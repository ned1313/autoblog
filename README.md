# Podcast-to-Blog Automation

An automated solution that transforms podcast episodes into blog posts using Azure Functions, Azure OpenAI, and GitHub integration.

## Overview

This project automates the process of creating blog posts from podcast episodes by:

1. Periodically checking a podcast RSS feed for new episodes
2. Retrieving transcripts when available
3. Generating well-structured blog posts using Azure OpenAI
4. Creating GitHub branches and pull requests to publish to your blog

## Architecture

- **Azure Function App**: Runs on a schedule to check for new podcast episodes
- **Azure OpenAI**: Processes transcripts and generates blog posts
- **Azure Key Vault**: Securely stores credentials and secrets
- **GitHub Integration**: Creates branches and pull requests for blog updates

## Prerequisites

- Azure subscription
- GitHub account with a repository for your blog
- GitHub Personal Access Token with repo permissions
- Terraform installed locally
- Azure CLI installed locally
- Podcast RSS feed URL

## Configuration

### Terraform Variables

The following variables can be customized in a `terraform.tfvars` file:

```hcl
project_name        = "autoblog"
environment         = "dev"
location            = "eastus"
podcast_rss_url     = "https://your-podcast-feed.com/rss"
github_repo_owner   = "your-github-username"
github_repo_name    = "your-blog-repo"
posts_path_pattern  = "content/posts"
github_token        = "your-github-personal-access-token"
```

### Blog Post Template

The blog post template can be customized in `src/function/templates/blog-template.md`.

## Deployment

1. Log in to Azure CLI:
   ```
   az login
   ```

2. Initialize Terraform:
   ```
   cd terraform
   terraform init
   ```

3. Plan the deployment:
   ```
   terraform plan -out=tfplan
   ```

4. Apply the Terraform configuration:
   ```
   terraform apply tfplan
   ```

5. Deploy the function code:
   ```
   cd ../src/function
   func azure functionapp publish <function-app-name>
   ```

## Local Development

1. Create a `local.settings.json` file in the `src/function` directory with your settings.

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the function locally:
   ```
   func start
   ```

## Customization

### Podcast Transcript Retrieval

The current implementation includes a placeholder for transcript retrieval. Customize the `get_transcript` function in `src/function/PodcastProcessor/__init__.py` to:

1. Use a specific podcast's transcript URL pattern
2. Integrate with a transcription service API
3. Parse HTML to extract embedded transcripts

### Blog Post Generation

The prompt for blog post generation can be customized in the `generate_blog_post` function to change the style, length, or format of the generated content.

## Monitoring and Troubleshooting

- **Application Insights**: The function app is integrated with Application Insights for monitoring
- **Function Logs**: View logs in the Azure Portal under the function app

## License

MIT
