provider "aws" {
  region = "us-east-2" 
}

# 1. Empacota o código da Lambda em um arquivo ZIP
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "src"
  output_path = "lambda_function_payload.zip"
}

# 2. Referencia o Role de Execução (Papel) existente
# O Terraform busca o ARN do Role que você já criou, eliminando a necessidade de criá-lo.
data "aws_iam_role" "existing_exec_role" {
  name = "chatbot-fiscal-processor-role-6s8yn1i1"
}

# 3. Define a função AWS Lambda
resource "aws_lambda_function" "minha_funcao_tf" {
  # A dependência 'depends_on' não é mais necessária, pois o Role já existe.
  
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "chatbot-fiscal-processor"
  # Usamos o ARN do Role existente
  role             = data.aws_iam_role.existing_exec_role.arn 
  handler          = "app.lambda_handler" 
  runtime          = "python3.13" 

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
}
