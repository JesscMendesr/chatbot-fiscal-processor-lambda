# Arquivo: backend.tf
# Configura o S3 como backend para armazenar o estado do Terraform
# Isso é crucial para que os deploys sejam rastreáveis e seguros.

terraform {
  backend "s3" {
    # Nome do Bucket S3 para armazenar o arquivo tfstate
    bucket = "fiscal-chatbot-jessica"
    
    # Chave (o caminho do arquivo state dentro do bucket)
    key    = "terraform/chatbot-fiscal-processor-lambda/terraform.tfstate"
    
    # Região do Bucket S3
    region = "us-east-2"
    
    # Tabela DynamoDB para Locking:
    # Garante que apenas um pipeline (ou usuário) faça o deploy por vez.
    # Você PRECISA criar essa tabela manualmente na AWS antes do primeiro `terraform init`.
    # O nome da tabela é geralmente: "terraform-locks" ou "tf-locks"
    dynamodb_table = "terraform-locks"
  }
}
