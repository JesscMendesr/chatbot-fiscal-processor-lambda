import json
import boto3
import requests
import re
from datetime import datetime
import uuid
import os

# --- CONFIGURAÇÕES GLOBAIS ---
# Agora, os valores são lidos das variáveis de ambiente da sua função Lambda
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
WHATSAPP_API_TOKEN = os.environ.get("WHATSAPP_API_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")

# URL da API do WhatsApp
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

# --- INICIALIZAÇÃO DE CLIENTES AWS ---
s3_client = boto3.client('s3')
textract_client = boto3.client('textract', region_name='us-east-2')
dynamodb = boto3.resource('dynamodb', region_name='us-east-2')

# --- FUNÇÕES AUXILIARES ---
# ---- TESTE DE DEPLOY NA AWS ----

def send_whatsapp_message(to_number, text):
    """Envia uma mensagem de texto via WhatsApp."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": text
        }
    }
    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        response.raise_for_status()
        print(f"Mensagem enviada. Status: {response.status_code}")
        return response.json()
    except requests.exceptions.HTTPError as err:
        print(f"Erro ao enviar mensagem HTTP: {err}")
    except Exception as err:
        print(f"Erro ao enviar mensagem: {err}")
        
def download_image(image_id):
    """Baixa a imagem da API do WhatsApp."""
    url = f"https://graph.facebook.com/v19.0/{image_id}"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        image_url = response.json()['url']
        
        image_response = requests.get(image_url, headers=headers)
        image_response.raise_for_status()
        print(f"URL da imagem: {image_url}")
        return image_response.content
    except Exception as e:
        print(f"Erro ao baixar a imagem: {e}")
        return None

def upload_to_s3(file_content, wa_id, image_id):
    """Salva o conteúdo da imagem em um bucket S3."""
    file_key = f"imagens/{wa_id}/{image_id}.jpg"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=file_key,
            Body=file_content,
            ContentType='image/jpeg'
        )
        print(f"Imagem salva no S3 como {file_key}")
        return file_key
    except Exception as e:
        print(f"Erro ao salvar a imagem no S3: {e}")
        return None

def parse_fiscal_note_v2(textract_response):
    """Analisa a resposta do Textract para extrair dados da nota fiscal."""
    parsed_data = {
        'total': None,
        'date': None,
        'cnpj': None
    }
    
    document_text = " ".join(item['Text'] for item in textract_response['Blocks'] if item['BlockType'] == 'LINE')
    document_text_upper = document_text.upper()

    cnpj_match = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', document_text_upper)
    if cnpj_match:
        parsed_data['cnpj'] = cnpj_match.group(1)

    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', document_text_upper)
    if date_match:
        parsed_data['date'] = date_match.group(1)
        
    total_match = re.search(r'(?:TOTAL|VALOR\sTOTAL)\s*(?:R\$)?\s*[\s\.:]*([\d\.]+,[\d]{2})', document_text_upper)
    if total_match:
        parsed_data['total'] = total_match.group(1).replace(',', '.')
    else:
        all_numbers_with_decimals = re.findall(r'(\d+[\.,]\d{2})', document_text_upper)
        if all_numbers_with_decimals:
            parsed_data['total'] = all_numbers_with_decimals[-1].replace(',', '.')

    return parsed_data

def register_user(from_number, cpf):
    """Salva o número de telefone do usuário e o CPF na tabela de usuários."""
    users_table = dynamodb.Table('invoice-extract-users')
    try:
        users_table.put_item(
            Item={
                'phone_number': from_number,
                'cpf': cpf
            }
        )
        print("Usuário cadastrado com sucesso.")
        return True
    except Exception as e:
        print(f"Erro ao cadastrar usuário: {e}")
        return False

def find_user_by_phone(from_number):
    """Busca o CPF de um usuário com base no número de telefone."""
    users_table = dynamodb.Table('invoice-extract-users')
    try:
        response = users_table.get_item(Key={'phone_number': from_number})
        if 'Item' in response:
            return response['Item']['cpf']
        return None
    except Exception as e:
        print(f"Erro ao buscar CPF do usuário: {e}")
        return None

def save_fiscal_note_to_db(cpf, parsed_data):
    """Salva os dados de uma nota fiscal no DynamoDB."""
    table = dynamodb.Table('fiscal-notes')
    print(f"Salvando dados da nota fiscal para o CPF: {cpf}")
    
    transaction_id = str(uuid.uuid4())
    
    item = {
        'cpf': cpf,
        'transaction_id': transaction_id,
        'total_value': parsed_data.get('total'),
        'date': parsed_data.get('date'),
        'cnpj': parsed_data.get('cnpj'),
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    try:
        table.put_item(Item=item)
        print("Dados salvos com sucesso no DynamoDB.")
    except Exception as e:
        print(f"Erro ao salvar dados no DynamoDB: {e}")

# --- LÓGICA DE PROCESSAMENTO DE MENSAGENS ---

def handle_image(from_number, image_id):
    """Processa a mensagem de imagem do usuário."""
    print("Recebi uma imagem! Processando...")
    file_content = download_image(image_id)
    if not file_content:
        send_whatsapp_message(from_number, "Desculpe, não consegui baixar a sua imagem.")
        return

    file_key = upload_to_s3(file_content, from_number, image_id)
    if not file_key:
        send_whatsapp_message(from_number, "Desculpe, não consegui salvar a imagem. Tente novamente mais tarde.")
        return
        
    textract_response = textract_client.detect_document_text(
        Document={
            'S3Object': {
                'Bucket': S3_BUCKET_NAME,
                'Name': file_key
            }
        }
    )

    parsed_data = parse_fiscal_note_v2(textract_response)

    user_cpf = find_user_by_phone(from_number)

    if parsed_data['total'] and parsed_data['date'] and user_cpf:
        send_whatsapp_message(from_number, f"Ótimo! Encontrei uma nota de R${parsed_data['total']} de {parsed_data['date']}. Vou registrar seus gastos.")
        save_fiscal_note_to_db(user_cpf, parsed_data)
    else:
        send_whatsapp_message(from_number, "Não consegui encontrar as informações importantes na sua nota. Por favor, tente enviar uma foto mais nítida. 🧐")

def handle_text_command(from_number, text_content):
    """Processa comandos de texto do usuário (futuras funcionalidades)."""
    if "oi" in text_content or "olá" in text_content:
        send_whatsapp_message(from_number, "Olá! Envie uma foto de sua nota fiscal para que eu possa registrar seus gastos.")
    else:
        send_whatsapp_message(from_number, "Não entendi a sua mensagem. Por favor, envie uma foto de sua nota fiscal.")


# --- FUNÇÃO PRINCIPAL DA LAMBDA ---
def lambda_handler(event, context):
    print("Recebi o evento:", json.dumps(event))
    try:
        body = json.loads(event.get('body', '{}'))
        if 'entry' not in body or not body['entry']:
            return {'statusCode': 200, 'body': 'ok'}

        changes = body['entry'][0]['changes'][0]

        if 'messages' in changes['value']:
            message = changes['value']['messages'][0]
            from_number = message['from']
            message_type = message['type']
            
            # Tenta encontrar o usuário pelo telefone
            user_cpf = find_user_by_phone(from_number)
            
            # --- Lógica de Cadastro/Processamento de Mensagens ---
            # SE o usuário NÃO tiver um CPF cadastrado
            if not user_cpf:
                if message_type == 'text':
                    # O usuário enviou um texto, que deve ser o CPF. Tenta registrar.
                    cpf_provided = message['text']['body'].strip()
                    
                    # Adiciona uma verificação simples para garantir que o texto é um CPF válido
                    if re.match(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', cpf_provided):
                        if register_user(from_number, cpf_provided):
                            send_whatsapp_message(from_number, "Cadastro realizado com sucesso! Pode me enviar a foto da sua primeira nota fiscal. 📸")
                        else:
                            send_whatsapp_message(from_number, "Desculpe, houve um erro ao tentar cadastrar seu CPF. Por favor, tente novamente.")
                    else:
                        send_whatsapp_message(from_number, "Olá! Para que eu possa registrar suas notas, preciso do seu CPF. Por favor, me informe o seu CPF completo. ✍️")
                        
                elif message_type == 'image':
                    # O usuário enviou uma imagem sem antes ter se cadastrado. Pede o CPF.
                    send_whatsapp_message(from_number, "Olá! Para que eu possa registrar suas notas, preciso do seu CPF. Por favor, me informe seu CPF antes de enviar a nota.")
                else:
                    # Qualquer outro tipo de mensagem de um novo usuário
                    send_whatsapp_message(from_number, "Olá! Para que eu possa registrar suas notas, preciso do seu CPF. Poderia me informar, por favor?")

            # SE o usuário JÁ TIVER um CPF cadastrado
            else:
                if message_type == 'image':
                    # O usuário enviou uma imagem. Processa a nota fiscal.
                    image_id = message['image']['id']
                    handle_image(from_number, image_id)
                elif message_type == 'text':
                    # O usuário enviou um comando de texto.
                    text_content = message['text']['body'].lower().strip()
                    handle_text_command(from_number, text_content)

    except Exception as e:
        print(f"Erro ao processar o evento: {e}")
        return {'statusCode': 200, 'body': 'ok'}

    return {'statusCode': 200, 'body': 'ok'}