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
from bs4 import BeautifulSoup

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
    """Extract transcript from the 'Episode Transcript' section of the podcast webpage."""
    try:
        logging.info(f"Fetching transcript from: {episode_url}")
        
        # Make a request to the episode URL
        response = requests.get(episode_url)
        if response.status_code != 200:
            logging.warning(f"Failed to fetch page: HTTP {response.status_code}")
            return None
            
        # Parse the HTML content with BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for a section titled "Episode Transcript"
        transcript_headers = []
        for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            if "episode transcript" in header.text.lower():
                transcript_headers.append(header)
                
        if transcript_headers:
            # Use the first matching header
            header = transcript_headers[0]
            transcript_text = []
            
            # Collect all paragraph elements that follow the header
            current = header.find_next()
            while current and current.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                if current.name == 'p':
                    transcript_text.append(current.get_text().strip())
                current = current.find_next()
                
            if transcript_text:
                return "\n\n".join(transcript_text)
        
        logging.warning("No transcript section found on the page")
        return None
    except Exception as e:
        logging.error(f"Error extracting transcript: {str(e)}")
        return None

def generate_blog_post(episode_title, episode_description, transcript, publish_date, template_content):
    """Generate a blog post from podcast transcript using Azure OpenAI."""
    try:
        client = init_openai_client()
        
        # GPT-4 Turbo model specs
        # Max input tokens: 128,000
        # Max output tokens: 4,096
        # Reserve tokens for system, prompt structure, and response
        model_name = os.environ["OPENAI_DEPLOYMENT_NAME"]
        max_output_tokens = int(os.environ.get("MAX_OUTPUT_TOKENS", "4000"))  # Default to slightly under the 4,096 limit
        
        # Estimate: 1 token ≈ 4 chars in English for input calculation
        # Reserve ~10,000 tokens for system prompt, task description, and metadata
        max_transcript_tokens = 118000  # 128k - 10k reserved
        max_transcript_chars = max_transcript_tokens * 4
        
        # Log original transcript size
        logging.info(f"Original transcript size: {len(transcript)} characters (approximately {len(transcript)//4} tokens)")
        
        # Truncate transcript if needed but retain as much as possible within token limits
        if len(transcript) > max_transcript_chars:
            logging.warning(f"Transcript exceeds token limit, truncating from {len(transcript)} to {max_transcript_chars} characters")
            truncated_transcript = transcript[:max_transcript_chars]
        else:
            truncated_transcript = transcript
        
        # Prepare prompt for blog post generation
        prompt = f"""
        Generate a well-structured, engaging blog post based on the following podcast episode:
        
        Title: {episode_title}
        Date: {publish_date.strftime('%Y-%m-%d')}
        Description: {episode_description}
        
        Transcript:
        {truncated_transcript}
        
        Instructions:
        1. Create a detailed summary in several substantive paragraphs
        2. Use a conversational, informative tone
        3. Include insights and key points from the podcast
        4. Make it engaging and accessible to readers who haven't listened to the podcast
        5. Format the output in markdown
        6. Include appropriate section headings
        7. If the transcript discusses code or technical concepts, include explanations
        8. The podcast is named "Day Two DevOps" and it is hosted by "Ned Bellavance" and "Kyler Middleton"
        9. The blog post will be published on Ned's blog at nedinthecloud.com
        10. The blog post should be SEO optimized for the title and keywords related to the podcast episode
        """
        
        # Generate content using Azure OpenAI
        logging.info(f"Calling Azure OpenAI with {len(truncated_transcript)//4} estimated tokens")
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are an expert content creator who transforms podcast transcripts into engaging blog posts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=max_output_tokens
        )
        
        # Extract content from response
        blog_content = response.choices[0].message.content.strip()
        logging.info(f"Generated blog content: {len(blog_content)} characters")
        
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
        
        # Calculate the time threshold (6 hours ago)
        time_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=6)
        logging.info(f"Looking for episodes published after: {time_threshold.isoformat()}")
        
        # Fetch and parse the RSS feed
        feed = fetch_rss_feed(podcast_rss_url)
        
        # Initialize GitHub client
        github_client = init_github_client()
        
        # Get the blog template
        template_content = get_template_content()
        
        # Process each episode in the feed
        for entry in feed.entries:
            # Parse publish date
            if hasattr(entry, 'published'):
                publish_date = parser.parse(entry.published)
                # Make sure the date has timezone info for comparison
                if publish_date.tzinfo is None:
                    publish_date = publish_date.replace(tzinfo=datetime.timezone.utc)
            else:
                logging.warning(f"Episode without publish date, skipping: {entry.title if hasattr(entry, 'title') else 'Unknown'}")
                continue
                
            # Skip episodes published before our time threshold
            if publish_date <= time_threshold:
                logging.info(f"Episode published before threshold ({publish_date.isoformat()}), skipping")
                continue
                
            episode_id = entry.id
            episode_title = entry.title
            episode_description = entry.description if hasattr(entry, 'description') else ""
            episode_link = entry.link
            
            logging.info(f"Processing new episode: {episode_title}, published at {publish_date.isoformat()}")
            
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
            year_str = publish_date.strftime('%Y')
            month_str = publish_date.strftime('%m')
            
            # Create a slug from the title
            slug = episode_title.lower().replace(" ", "-")
            slug = ''.join(c if c.isalnum() or c == '-' else '' for c in slug)
            
            # Parse the path pattern and replace placeholders
            file_path = posts_path_pattern
            # Replace YYYY with the year
            file_path = file_path.replace("YYYY", year_str)
            # Replace MM with the month
            file_path = file_path.replace("MM", month_str)
            # Replace post-title with the slug
            file_path = file_path.replace("post-title", slug)
            
            logging.info(f"Generated file path: {file_path}")
            
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
                
                logging.info(f"Successfully processed episode: {episode_title}")
            else:
                logging.warning(f"Skipped creating pull request for {episode_title} as file already exists")
        
        logging.info('Podcast processing completed successfully')
    except Exception as e:
        logging.error(f"Error in podcast processor function: {str(e)}")
        raise