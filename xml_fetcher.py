import requests
import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime

JSON_FILE = "data_desmobja.json"

# =================== UTILS =======================

def converter_preco(preco_str):
    """Converte preço do XML para inteiro"""
    if not preco_str:
        return 0
    try:
        valor = float(str(preco_str))
        # Se o valor parece estar em centavos (muito alto), divide por 100
        if valor > 1000000:
            valor = valor / 100
        return int(valor)  # Retorna como inteiro
    except (ValueError, TypeError):
        return 0

def converter_km(km_str):
    """Converte KM para inteiro"""
    if not km_str:
        return 0
    try:
        return int(str(km_str))
    except (ValueError, TypeError):
        return 0

# =================== FETCHER SIMPLES =======================

def get_xml_url():
    """Pega URL do XML da variável de ambiente"""
    return os.environ.get("XML_URL_DESMOBJA", "https://n8n-n8n-start.xnvwew.easypanel.host/webhook/xml")

def fetch_and_convert_xml():
    try:
        XML_URL = get_xml_url()
        print(f"[INFO] Buscando XML de: {XML_URL}")
        
        response = requests.get(XML_URL, timeout=30)
        response.raise_for_status()
        
        # Parse do XML
        root = ET.fromstring(response.content)
        
        veiculos = []
        
        # Extrair cada veículo do XML
        for veiculo in root.findall('.//veiculo'):
            veiculo_data = {}
            
            # Extrair todos os campos diretamente
            for campo in veiculo:
                tag_name = campo.tag
                tag_value = campo.text if campo.text else ""
                
                # Conversões específicas
                if tag_name == "preco":
                    veiculo_data[tag_name] = converter_preco(tag_value)
                elif tag_name == "km":
                    veiculo_data[tag_name] = converter_km(tag_value)
                elif tag_name == "sequencia":
                    veiculo_data[tag_name] = int(tag_value) if tag_value.isdigit() else tag_value
                else:
                    veiculo_data[tag_name] = tag_value
            
            veiculos.append(veiculo_data)
        
        # Extrair metadados do estoque
        data_geracao = root.find('dataGeracao')
        total_veiculos = root.find('totalVeiculos')
        
        data_dict = {
            "veiculos": veiculos,
            "total_veiculos": int(total_veiculos.text) if total_veiculos is not None else len(veiculos),
            "data_geracao": data_geracao.text if data_geracao is not None else None,
            "_updated_at": datetime.now().isoformat()
        }
        
        # Salvar JSON
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] {len(veiculos)} veículos convertidos com sucesso.")
        print(f"[OK] Arquivo salvo: {JSON_FILE}")
        
        return data_dict
        
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao buscar XML: {e}")
        return {}
    except ET.ParseError as e:
        print(f"[ERRO] Falha ao fazer parse do XML: {e}")
        return {}
    except Exception as e:
        print(f"[ERRO] Falha geral: {e}")
        return {}

# =================== MAIN =======================

if __name__ == "__main__":
    result = fetch_and_convert_xml()
    if result:
        print(f"[SUCCESS] Processados {len(result.get('veiculos', []))} veículos")
    else:
        print("[FAIL] Nenhum veículo processado")
