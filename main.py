import json
import datetime
import os
from flask import request as flask_request
from flask import jsonify
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

# Configura las credenciales de almacenamiento en la nube de Google Cloud
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'C:/service-account-key.json'

def main(request):
    try:
        # Asegúrate de que la solicitud es una solicitud POST
        if flask_request.method != 'POST':
            return {
                'statusCode': 405,
                'body': "This endpoint only supports POST requests."
            }

        # Leer el archivo de la imagen desde los datos del formulario 'form-data'
        if 'file' not in flask_request.files:
            return {
                'statusCode': 400,
                'body': "Please upload the file with the 'file' key in form-data."
            }

        file = flask_request.files['file']
        image_bytes = file.read()

        # Procesar la imagen y obtener el resultado
        result = analizar_ticket(image_bytes)
        json_result = json.dumps(result)

        # Imprimir el resultado en la consola para propósitos de depuración
        print(f'Resultado del análisis de la imagen: {json_result}')

        return jsonify(result), 200
    except Exception as e:
        return {
            'statusCode': 400,
            'body': f"Error reading image file: {str(e)}"
        }

def convertir_fecha(fecha_str):

    meses = {
        "Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04", "Mayo": "05", "Junio": "06",
        "Julio": "07", "Agosto": "08", "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"
    }

    formatos_posibles = [
        '%d/%B/%Y',   
        '%d/%m/%y',   
        '%d-%m-%y',   
    ]

    for formato in formatos_posibles:
        try:
            if formato == '%d/%B/%Y':
                dia, mes_str, año = fecha_str.split('/')
                mes = meses.get(mes_str, mes_str)
                fecha_formateada = f"{año}-{mes}-{dia}"
                return fecha_formateada
            else:
                fecha_formateada = datetime.strptime(fecha_str, formato)
                return fecha_formateada.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ""

def analizar_ticket(image_bytes):
    endpoint = "https://citcognitiveservicedev.cognitiveservices.azure.com"
    key = "586bf736a33a4b8b8795ddd9d4aeb2e7"

    document_analysis_client = DocumentAnalysisClient(
        endpoint=endpoint, credential=AzureKeyCredential(key)
    )

    poller = document_analysis_client.begin_analyze_document("prebuilt-receipt", image_bytes)
    receipts = poller.result()

    tipo_registro_map = {
        "receipt.retailMeal": "Comida",
        "receipt.creditCard": "Varios",
        "receipt.gas": "Transporte",
        "receipt.parking": "Varios",
        "receipt.hotel": "Hospedaje"
    }

    output = []
    for receipt in receipts.documents:
        fields = {
            "MerchantName": receipt.fields.get("MerchantName"),
            "MerchantAddress": receipt.fields.get("MerchantAddress"),
            "TransactionDate": receipt.fields.get("TransactionDate"),
            "TransactionTime": receipt.fields.get("TransactionTime"),
            "Total": receipt.fields.get("Total")
        }

        confident_fields = {
            key: value for key, value in fields.items() if value and value.confidence >= 0.5
        }

        merchant_address_line = ""
        if "MerchantAddress" in confident_fields:
            merchant_address_value = confident_fields["MerchantAddress"].value
            address_components = [
                merchant_address_value.house_number,
                merchant_address_value.road,
                merchant_address_value.city,
                merchant_address_value.state,
                merchant_address_value.postal_code,
                merchant_address_value.country_region,
                merchant_address_value.street_address,
            ]
            full_address = " ".join(filter(None, address_components))
            merchant_address_line = full_address

        tipo_registro = tipo_registro_map.get(receipt.doc_type, "Otro")

        transaction_date = ""
        transaction_time = ""
        transaction_date_value = confident_fields.get('TransactionDate')
        transaction_time_value = confident_fields.get('TransactionTime')

        if transaction_date_value and hasattr(transaction_date_value, 'content'):
            transaction_date = convertir_fecha(transaction_date_value.content)

        if transaction_time_value and hasattr(transaction_time_value, 'content'):
            # Aquí asumimos que el tiempo ya está en un formato adecuado
            transaction_time = transaction_time_value.content

        # Concatenando fecha y hora
        fecha_y_hora = f"{transaction_date} {transaction_time}".strip()

        receipt_info = {
            "TipoRegistro": tipo_registro,
            "NombreComerciante": confident_fields['MerchantName'].value if "MerchantName" in confident_fields else "",
            "LugarComerciante": merchant_address_line,
            "Fecha": fecha_y_hora,
            "Importe": confident_fields['Total'].value if "Total" in confident_fields else "",
            "Descripcion": "",
        }

        output.append(receipt_info)

    return output