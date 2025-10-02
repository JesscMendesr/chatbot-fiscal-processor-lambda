# Arquivo: main.tf

provider "aws" {
  region = "us-east-2" # SUBSTITUA pela sua região
}

# 1. Empacota o código da Lambda em um arquivo ZIP
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "src"
  output_path = "lambda_function_payload.zip"
}

# 2. Cria o Role (Papel) de Execução da Lambda
resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda-tf-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# 3. Anexa a permissão para escrever logs no CloudWatch
resource "aws_iam_role_policy_attachment" "lambda_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# 4. Define a função AWS Lambda
resource "aws_lambda_function" "minha_funcao_tf" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "chatbot-fiscal-processor"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "app.lambda_handler" # Ex: nome_arquivo.nome_funcao
  runtime          = "python3.13"          # SUBSTITUA pela sua linguagem (nodejs18.x, java17, etc.)

  # Garante que a Lambda só é atualizada se o conteúdo do ZIP mudar
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
}