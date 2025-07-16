import requests
import xml.etree.ElementTree as ET
import json
import os
from typing import List, Dict, Any

def get_xml_urls():
    """Pega URLs do XML das variáveis de ambiente"""
    urls = []
    
    # Primeiro, pega XML_URL se existir
    xml_url = os.environ.get("XML_URL")
    if xml_url and xml_url.strip():
        urls.append(xml_url.strip())
        print(f"[DEBUG] Encontrou XML_URL: {xml_url.strip()}")
    
    # Depois, pega outras variáveis que começam com XML_URL
    for var, val in os.environ.items():
        if var.startswith("XML_URL") and var != "XML_URL" and val and val.strip():
            clean_url = val.strip()
            if clean_url not in urls:  # Evita duplicatas
                urls.append(clean_url)
                print(f"[DEBUG] Encontrou {var}: {clean_url}")
    
    print(f"[DEBUG] Total de URLs encontradas: {len(urls)}")
    return urls

def fetch_xml_from_url(url: str) -> str:
    """Busca XML de uma URL específica"""
    try:
        print(f"[INFO] Buscando XML de: {url}")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        xml_content = response.text
        print(f"[INFO] XML obtido com sucesso: {len(xml_content)} caracteres")
        
        return xml_content
        
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao buscar XML de {url}: {e}")
        return None

def parse_xml_to_json(xml_content: str) -> Dict[str, Any]:
    """Converte XML para formato JSON"""
    try:
        # Parse do XML
        root = ET.fromstring(xml_content)
        
        # Verifica se é o formato esperado
        if root.tag != 'estoque':
            print(f"[ERRO] Formato XML inesperado. Tag raiz: {root.tag}")
            return {"veiculos": []}
        
        # Pega informações do cabeçalho
        data_geracao = root.findtext('dataGeracao', '')
        total_veiculos = root.findtext('totalVeiculos', '0')
        
        print(f"[INFO] Data geração: {data_geracao}")
        print(f"[INFO] Total veículos no XML: {total_veiculos}")
        
        veiculos = []
        
        # Processa cada veículo
        veiculos_xml = root.find('veiculos')
        if veiculos_xml is not None:
            for veiculo_xml in veiculos_xml.findall('veiculo'):
                veiculo = {}
                
                # Extrai todos os campos do veículo
                for child in veiculo_xml:
                    tag = child.tag
                    text = child.text or ""
                    
                    # Remove CDATA se presente
                    if text.startswith('<![CDATA[') and text.endswith(']]>'):
                        text = text[9:-3]
                    
                    veiculo[tag] = text.strip()
                
                # Converte tipos quando necessário
                if 'sequencia' in veiculo:
                    try:
                        veiculo['sequencia'] = int(veiculo['sequencia'])
                    except ValueError:
                        pass
                
                if 'km' in veiculo and veiculo['km']:
                    try:
                        # Remove pontos e vírgulas se houver
                        km_clean = veiculo['km'].replace('.', '').replace(',', '')
                        veiculo['km'] = int(km_clean)
                    except ValueError:
                        pass
                
                # Adiciona campos padrão se não existirem
                if 'placa' not in veiculo:
                    veiculo['placa'] = ''
                if 'modelo' not in veiculo:
                    veiculo['modelo'] = veiculo.get('veiculo', '')
                if 'valorIdealVenda' not in veiculo:
                    veiculo['valorIdealVenda'] = ''
                
                veiculos.append(veiculo)
        
        print(f"[INFO] Processados {len(veiculos)} veículos do XML")
        
        # Log dos primeiros veículos para debug
        if veiculos:
            primeiro = veiculos[0]
            print(f"[DEBUG] Primeiro veículo: {primeiro.get('placa', 'N/A')} - {primeiro.get('modelo', primeiro.get('veiculo', 'N/A'))}")
            print(f"[DEBUG] Campos disponíveis: {list(primeiro.keys())}")
        
        return {
            "veiculos": veiculos,
            "total": len(veiculos),
            "data_atualizacao": data_geracao,
            "total_xml": total_veiculos,
            "fonte": "pipefy_xml"
        }
        
    except ET.ParseError as e:
        print(f"[ERRO] Erro ao fazer parse do XML: {e}")
        print(f"[DEBUG] Primeiros 500 caracteres do XML: {xml_content[:500]}")
        return {"veiculos": []}
    except Exception as e:
        print(f"[ERRO] Erro inesperado ao processar XML: {e}")
        return {"veiculos": []}

def fetch_and_convert_xml():
    """Função principal que busca XMLs e converte para JSON"""
    try:
        # Pega as URLs configuradas
        urls = get_xml_urls()
        
        if not urls:
            print("[ERRO] Nenhuma URL de XML configurada")
            return
        
        print(f"[INFO] URLs encontradas: {urls}")
        
        all_vehicles = []
        successful_fetches = 0
        
        # Processa cada URL individualmente
        for url in urls:
            # Garante que url é string, não lista
            if isinstance(url, list):
                print(f"[ERRO] URL inválida (lista): {url}")
                continue
                
            url_str = str(url).strip()
            print(f"[INFO] Processando: {url_str}")
            
            xml_content = fetch_xml_from_url(url_str)
            if xml_content:
                data = parse_xml_to_json(xml_content)
                vehicles = data.get("veiculos", [])
                
                if vehicles:
                    all_vehicles.extend(vehicles)
                    successful_fetches += 1
                    print(f"[INFO] {len(vehicles)} veículos adicionados de {url_str}")
                else:
                    print(f"[AVISO] Nenhum veículo encontrado em {url_str}")
            else:
                print(f"[ERRO] Falha ao obter XML de {url_str}")
        
        # Salva os dados no arquivo JSON
        if all_vehicles:
            output_data = {
                "veiculos": all_vehicles,
                "total": len(all_vehicles),
                "fontes_processadas": successful_fetches,
                "total_fontes": len(urls),
                "ultima_atualizacao": None
            }
            
            # Pega data de geração do primeiro XML se disponível
            if urls and successful_fetches > 0:
                try:
                    xml_content = fetch_xml_from_url(urls[0])
                    if xml_content:
                        root = ET.fromstring(xml_content)
                        data_geracao = root.findtext('dataGeracao', '')
                        if data_geracao:
                            output_data["ultima_atualizacao"] = data_geracao
                except:
                    pass
            
            # Salva no arquivo
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            print(f"[SUCESSO] {len(all_vehicles)} veículos salvos em data.json")
            print(f"[INFO] Fontes processadas: {successful_fetches}/{len(urls)}")
            
        else:
            print("[ERRO] Nenhum veículo foi carregado de nenhuma fonte")
            # Cria arquivo vazio para evitar erros
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump({"veiculos": [], "total": 0}, f)
    
    except Exception as e:
        print(f"[ERRO] Falha geral: {e}")
        # Cria arquivo vazio em caso de erro
        try:
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump({"veiculos": [], "total": 0}, f)
        except:
            pass

if __name__ == "__main__":
    fetch_and_convert_xml()
