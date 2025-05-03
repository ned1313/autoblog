# deploy.ps1 - Deployment script for Podcast-to-Blog Automation solution

# Display banner
Write-Host "================================================"
Write-Host "  Podcast-to-Blog Automation Deployment Script  "
Write-Host "================================================"
Write-Host

# Check for required commands
Write-Host "Checking prerequisites..."
$commands = @("az", "terraform", "func")
foreach ($cmd in $commands) {
    if (!(Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Error: $cmd is required but not installed." -ForegroundColor Red
        Write-Host "Please install the required dependencies and try again."
        exit 1
    }
}

# Check if logged in to Azure
Write-Host "Checking Azure login..."
try {
    $null = az account show
    Write-Host "Already logged in to Azure." -ForegroundColor Green
}
catch {
    Write-Host "You need to log in to Azure first." -ForegroundColor Yellow
    az login
}

# Terraform deployment
Set-Location -Path "$PSScriptRoot\terraform"

Write-Host "Initializing Terraform..."
terraform init

Write-Host "Validating Terraform configuration..."
terraform validate

Write-Host "Creating Terraform plan..."
terraform plan -out=tfplan

Write-Host "Apply Terraform plan? (y/n)" -ForegroundColor Yellow
$applyChoice = Read-Host
if ($applyChoice -eq "y" -or $applyChoice -eq "Y") {
    Write-Host "Applying Terraform plan..."
    terraform apply tfplan
    
    # Get function app name from Terraform output
    $functionAppName = terraform output -raw function_app_name
    
    # Package and deploy the Azure Function
    Write-Host "Deploying Azure Function to $functionAppName..." -ForegroundColor Cyan
    Set-Location -Path "$PSScriptRoot\src\function"
    
    Write-Host "Installing Python dependencies..."
    pip install -r requirements.txt
    
    Write-Host "Publishing function to Azure..."
    func azure functionapp publish $functionAppName --python
    
    Write-Host "Deployment completed successfully!" -ForegroundColor Green
    Write-Host "Function App URL: https://$functionAppName.azurewebsites.net" -ForegroundColor Cyan
}
else {
    Write-Host "Terraform apply cancelled." -ForegroundColor Yellow
}

# Return to original directory
Set-Location -Path $PSScriptRoot