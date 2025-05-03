import logging
import os
import json
import datetime
import azure.functions as func
from dateutil import parser
import feedparser
import requests
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from openai import AzureOpenAI
from github import Github, GithubException
from jinja2 import Template

# Configure the function app
app = func.FunctionApp()

# Setup logging
logger = logging.getLogger('podcast-processor')

def get_secret_from_keyvault(secret_name):
    """Get a secret from Key Vault using managed identity."""
    try:
        key_vault_name = os.environ["KeyVaultName"]
        key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"
        
        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)
        
        return secret_client.get_secret(secret_name).value
    except Exception as e:
        logger.error(f"Error retrieving secret from Key Vault: {str(e)}")
        raise

def init_openai_client():
    """Initialize the Azure OpenAI client."""
    try:
        endpoint = os.environ["OPENAI_ENDPOINT"]
        deployment_name = os.environ["OPENAI_DEPLOYMENT_NAME"]
        
        # Use managed identity
        credential = DefaultAzureCredential()
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_deployment=deployment_name,
            credential=credential
        )
        return client
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {str(e)}")
        raise

def init_github_client():
    """Initialize the GitHub client using token from Key Vault."""
    try:
        github_token = get_secret_from_keyvault("github-token")
        return Github(github_token)
    except Exception as e:
        logger.error(f"Error initializing GitHub client: {str(e)}")
        raise

def fetch_rss_feed(rss_url):
    """Fetch and parse RSS feed."""
    try:
        return feedparser.parse(rss_url)
    except Exception as e:
        logger.error(f"Error fetching RSS feed: {str(e)}")
        raise

def get_transcript(episode_url):
    """Attempt to fetch transcript from podcast URL."""
    try:
        # This is a placeholder. In real implementation, you would:
        # 1. Check if transcript exists at a known URL pattern based on episode URL
        # 2. Potentially use a transcription service if not available
        
        # For demonstration, we'll just make a request to the episode URL
        # and assume a transcript might be in the HTML or linked
        response = requests.get(episode_url)
        
        # In a real implementation, you would parse the page to find the transcript
        # For now, returning a placeholder message
        if response.status_code == 200:
            # This would be replaced with actual transcript extraction logic
            return f"Placeholder transcript for episode at {episode_url}. In a real implementation, this would be the actual transcript text extracted from the page or a linked transcript file."
        else:
            return None
    except Exception as e:
        logger.error(f"Error fetching transcript: {str(e)}")
        return None

def generate_blog_post(episode_title, episode_description, transcript, publish_date, template_content):
    """Generate a blog post from podcast transcript using Azure OpenAI."""
    try:
        client = init_openai_client()
        
        # Calculate appropriate token budget
        # Estimate: 1 token ≈ 4 chars in English, reserve about 1500 tokens for response
        max_transcript_tokens = 12000  # 16k context - tokens for system, prompt, and response
        
        # Truncate transcript if needed but retain as much as possible within token limits
        transcript_chars = min(len(transcript), max_transcript_tokens * 4)
        truncated_transcript = transcript[:transcript_chars]
        
        # Prepare prompt for blog post generation
        prompt = f"""
        Generate a well-structured, engaging blog post based on the following podcast episode:
        
        Title: {episode_title}
        Date: {publish_date.strftime('%Y-%m-%d')}
        Description: {episode_description}
        
        Transcript:
        {truncated_transcript}
        
        Instructions:
        1. Create a detailed summary in five substantive paragraphs
        2. Use a conversational, informative tone
        3. Include insights and key points from the podcast
        4. Make it engaging and accessible to readers who haven't listened to the podcast
        5. Format the output in markdown
        """
        
        # Generate content using Azure OpenAI
        response = client.chat.completions.create(
            model=os.environ["OPENAI_DEPLOYMENT_NAME"],
            messages=[
                {"role": "system", "content": "You are an expert content creator who transforms podcast transcripts into engaging blog posts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        # Extract content from response
        blog_content = response.choices[0].message.content.strip()
        
        # Render the template with the generated content
        template = Template(template_content)
        rendered_post = template.render(
            title=episode_title,
            date=publish_date.strftime('%Y-%m-%d'),
            content=blog_content
        )
        
        return rendered_post
    except Exception as e:
        logger.error(f"Error generating blog post: {str(e)}")
        raise

def create_github_branch(github_client, repo_owner, repo_name, base_branch, new_branch):
    """Create a new branch in GitHub repository."""
    try:
        repo = github_client.get_repo(f"{repo_owner}/{repo_name}")
        
        # Get the reference of the base branch
        base_ref = repo.get_git_ref(f"heads/{base_branch}")
        
        # Create new branch reference
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_ref.object.sha)
        
        return repo
    except GithubException as e:
        if e.status == 422:  # Branch already exists
            logger.warning(f"Branch '{new_branch}' already exists, using existing branch")
            return github_client.get_repo(f"{repo_owner}/{repo_name}")
        else:
            logger.error(f"Error creating GitHub branch: {str(e)}")
            raise
    except Exception as e:
        logger.error(f"Error creating GitHub branch: {str(e)}")
        raise

def create_blog_post_file(repo, branch, file_path, content, commit_message):
    """Create a new file in the GitHub repository."""
    try:
        repo.create_file(
            path=file_path,
            message=commit_message,
            content=content,
            branch=branch
        )
        logger.info(f"Created file: {file_path}")
        return True
    except GithubException as e:
        if e.status == 422:  # File already exists
            logger.warning(f"File '{file_path}' already exists")
            return False
        else:
            logger.error(f"Error creating file in GitHub: {str(e)}")
            raise
    except Exception as e:
        logger.error(f"Error creating file in GitHub: {str(e)}")
        raise

def create_pull_request(repo, base_branch, head_branch, title, body):
    """Create a pull request in GitHub repository."""
    try:
        pr = repo.create_pull(
            title=title,
            body=body,
            base=base_branch,
            head=head_branch
        )
        logger.info(f"Created PR #{pr.number}: {pr.html_url}")
        return pr
    except GithubException as e:
        # Check if PR already exists
        if e.status == 422:
            logger.warning("A pull request might already exist for this branch")
        logger.error(f"Error creating pull request: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error creating pull request: {str(e)}")
        raise

def get_template_content():
    """Get blog post template."""
    # This could be stored in blob storage or another location
    # For simplicity, we'll use a basic template here
    template = """---
title: "{{ title }}"
date: {{ date }}
draft: false
---

{{ content }}
"""
    return template

def save_processed_episodes(episodes_data):
    """Save information about processed episodes to avoid reprocessing."""
    try:
        with open("processed_episodes.json", "w") as f:
            json.dump(episodes_data, f)
    except Exception as e:
        logger.error(f"Error saving processed episodes: {str(e)}")

def load_processed_episodes():
    """Load information about previously processed episodes."""
    try:
        if os.path.exists("processed_episodes.json"):
            with open("processed_episodes.json", "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading processed episodes: {str(e)}")
        return {}

@app.function_name("PodcastProcessor")
@app.schedule(schedule=os.environ.get("SCHEDULE", "0 0 */6 * * *"), arg_name="timer", run_on_startup=True)
def podcast_processor(timer: func.TimerRequest) -> None:
    """
    Azure Function that runs on a schedule to check for new podcast episodes,
    generate blog posts, and create pull requests.
    """
    if timer.past_due:
        logging.info('The timer is past due!')
    
    logging.info('Starting podcast processing function')
    
    try:
        # Environment variables
        podcast_rss_url = os.environ["PODCAST_RSS_URL"]
        github_repo_owner = os.environ["GITHUB_REPO_OWNER"]
        github_repo_name = os.environ["GITHUB_REPO_NAME"]
        posts_path_pattern = os.environ.get("POSTS_PATH_PATTERN", "content/posts")
        
        # Load previously processed episodes
        processed_episodes = load_processed_episodes()
        
        # Fetch and parse the RSS feed
        feed = fetch_rss_feed(podcast_rss_url)
        
        # Initialize GitHub client
        github_client = init_github_client()
        
        # Get the blog template
        template_content = get_template_content()
        
        # Process each episode in the feed
        for entry in feed.entries:
            episode_id = entry.id
            
            # Skip if already processed
            if episode_id in processed_episodes:
                logging.info(f"Episode {episode_id} already processed, skipping")
                continue
            
            episode_title = entry.title
            episode_description = entry.description if hasattr(entry, 'description') else ""
            episode_link = entry.link
            publish_date = parser.parse(entry.published) if hasattr(entry, 'published') else datetime.datetime.now()
            
            logging.info(f"Processing episode: {episode_title}")
            
            # Get transcript
            transcript = get_transcript(episode_link)
            if not transcript:
                logging.warning(f"Could not find transcript for {episode_title}, skipping")
                continue
            
            # Generate blog post
            blog_post_content = generate_blog_post(
                episode_title,
                episode_description,
                transcript,
                publish_date,
                template_content
            )
            
            # Format date for file naming
            date_str = publish_date.strftime('%Y-%m-%d')
            
            # Create a slug from the title
            slug = episode_title.lower().replace(" ", "-")
            slug = ''.join(c if c.isalnum() or c == '-' else '' for c in slug)
            
            # File path in the GitHub repo
            file_path = f"{posts_path_pattern}/{date_str}-{slug}.md"
            
            # Branch name
            branch_name = f"podcast-post-{date_str}-{slug[:20]}"
            
            # Create a new branch
            repo = create_github_branch(
                github_client,
                github_repo_owner,
                github_repo_name,
                "main",  # Assuming main is the default branch
                branch_name
            )
            
            # Create file with blog post content
            file_created = create_blog_post_file(
                repo,
                branch_name,
                file_path,
                blog_post_content,
                f"Add blog post for podcast episode: {episode_title}"
            )
            
            if file_created:
                # Create a pull request
                pr = create_pull_request(
                    repo,
                    "main",
                    branch_name,
                    f"Add blog post for podcast: {episode_title}",
                    f"Automatically generated blog post from podcast episode published on {date_str}."
                )
                
                # Mark episode as processed
                processed_episodes[episode_id] = {
                    "title": episode_title,
                    "date": date_str,
                    "file_path": file_path,
                    "pr_number": pr.number if pr else None,
                    "processed_at": datetime.datetime.now().isoformat()
                }
                
                # Save updated processed episodes list
                save_processed_episodes(processed_episodes)
                
                logging.info(f"Successfully processed episode: {episode_title}")
            else:
                logging.warning(f"Skipped creating pull request for {episode_title} as file already exists")
        
        logging.info('Podcast processing completed successfully')
    except Exception as e:
        logging.error(f"Error in podcast processor function: {str(e)}")
        raise