#!/bin/bash
# deploy.sh - Deployment script for Podcast-to-Blog Automation solution

# Display banner
echo "================================================"
echo "  Podcast-to-Blog Automation Deployment Script  "
echo "================================================"
echo

# Check for required commands
echo "Checking prerequisites..."
commands=("az" "terraform" "func")
for cmd in "${commands[@]}"; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd is required but not installed."
        echo "Please install the required dependencies and try again."
        exit 1
    fi
done

# Check if logged in to Azure
echo "Checking Azure login..."
if ! az account show &> /dev/null; then
    echo "You need to log in to Azure first."
    az login
else 
    echo "Already logged in to Azure."
fi

# Terraform deployment
cd terraform

echo "Initializing Terraform..."
terraform init

echo "Validating Terraform configuration..."
terraform validate

echo "Creating Terraform plan..."
terraform plan -out=tfplan

echo "Apply Terraform plan? (y/n)"
read -r apply_choice
if [[ $apply_choice == "y" || $apply_choice == "Y" ]]; then
    echo "Applying Terraform plan..."
    terraform apply tfplan
    
    # Get function app name from Terraform output
    function_app_name=$(terraform output -raw function_app_name)
    
    # Package and deploy the Azure Function
    echo "Deploying Azure Function to $function_app_name..."
    cd ../src/function
    
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
    
    echo "Publishing function to Azure..."
    func azure functionapp publish "$function_app_name" --python
    
    echo "Deployment completed successfully!"
    echo "Function App URL: https://$function_app_name.azurewebsites.net"
else
    echo "Terraform apply cancelled."
    exit 0
fi