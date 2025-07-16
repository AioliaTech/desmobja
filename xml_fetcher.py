import xml.etree.ElementTree as ET
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Configuração da URL do XML - MODIFIQUE AQUI
XML_URL = "https://sua-url-aqui.com/estoque.xml"  # 🔧 SUBSTITUA PELA SUA URL

class XMLFetcher:
    def __init__(self, xml_source: str = None, is_url: bool = None):
        """
        Inicializa o XMLFetcher
        
        Args:
            xml_source (str): Caminho para o arquivo XML ou URL (opcional, usa XML_URL se None)
            is_url (bool): Se True, xml_source é tratado como URL (auto-detecta se None)
        """
        # Se não especificado, usa a URL configurada
        if xml_source is None:
            xml_source = XML_URL
            is_url = True
        
        # Auto-detecta se é URL
        if is_url is None:
            is_url = xml_source.startswith(('http://', 'https://'))
        
        self.xml_source = xml_source
        self.is_url = is_url
        self.data = None
        self.logger = logging.getLogger(__name__)
        self._last_xml_content = None
    
    def download_xml(self, timeout: int = 30) -> str:
        """
        Baixa o XML de uma URL
        
        Args:
            timeout (int): Timeout em segundos
            
        Returns:
            str: Conteúdo XML como string
        """
        try:
            self.logger.info(f"Baixando XML de: {self.xml_source}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(self.xml_source, timeout=timeout, headers=headers)
            response.raise_for_status()
            
            # Verifica se é XML válido
            if 'xml' not in response.headers.get('content-type', '').lower():
                # Tenta verificar se o conteúdo parece XML
                content = response.text.strip()
                if not content.startswith('<?xml') and not content.startswith('<'):
                    raise ValueError("Resposta não parece ser XML válido")
            
            self.logger.info(f"XML baixado com sucesso: {len(response.text)} caracteres")
            
            # Armazena conteúdo para backup
            self._last_xml_content = response.text
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Erro ao baixar XML: {e}")
        except Exception as e:
            raise Exception(f"Erro inesperado ao baixar XML: {e}")
    
    def parse_xml(self) -> Dict:
        """
        Faz o parse do XML e converte para um dicionário Python
        
        Returns:
            Dict: Dados do estoque em formato de dicionário
        """
        try:
            if self.is_url:
                # Baixa XML da URL
                xml_content = self.download_xml()
                root = ET.fromstring(xml_content)
            else:
                # Carrega XML do arquivo local
                tree = ET.parse(self.xml_source)
                root = tree.getroot()
            
            # Extrai informações gerais do estoque
            estoque_data = {
                'dataGeracao': self._get_element_text(root, 'dataGeracao'),
                'totalVeiculos': self._get_element_text(root, 'totalVeiculos', int),
                'veiculos': [],
                'fonte': self.xml_source,
                'dataProcessamento': datetime.now().isoformat()
            }
            
            # Processa cada veículo
            veiculos_element = root.find('veiculos')
            if veiculos_element is not None:
                for veiculo in veiculos_element.findall('veiculo'):
                    veiculo_data = self._parse_veiculo(veiculo)
                    estoque_data['veiculos'].append(veiculo_data)
            
            self.data = estoque_data
            self.logger.info(f"XML processado: {len(estoque_data['veiculos'])} veículos")
            return estoque_data
            
        except ET.ParseError as e:
            raise ValueError(f"Erro ao fazer parse do XML: {e}")
        except FileNotFoundError:
            raise FileNotFoundError(f"Arquivo XML não encontrado: {self.xml_source}")
        except Exception as e:
            raise Exception(f"Erro inesperado ao processar XML: {e}")
    
    def _parse_veiculo(self, veiculo_element: ET.Element) -> Dict:
        """
        Processa um elemento veículo individual
        
        Args:
            veiculo_element (ET.Element): Elemento XML do veículo
            
        Returns:
            Dict: Dados do veículo
        """
        veiculo_data = {
            'sequencia': self._get_element_text(veiculo_element, 'sequencia', int),
            'placa': self._get_element_text(veiculo_element, 'placa'),
            'modelo': self._get_element_text(veiculo_element, 'modelo'),
            'cor': self._get_element_text(veiculo_element, 'cor'),
            'ano': self._get_element_text(veiculo_element, 'ano'),
            'km': self._get_element_text(veiculo_element, 'km', int),
            'preco': self._get_element_text(veiculo_element, 'preco', int),
            'linkMaterialDivulgacao': self._get_element_text(veiculo_element, 'linkMaterialDivulgacao'),
            'dataEntrada': self._get_element_text(veiculo_element, 'dataEntrada'),
            'checklistPdf': self._get_element_text(veiculo_element, 'checklistPdf')
        }
        
        return veiculo_data
    
    def _get_element_text(self, parent: ET.Element, tag: str, convert_type: type = str) -> Optional:
        """
        Extrai texto de um elemento XML com conversão de tipo opcional
        
        Args:
            parent (ET.Element): Elemento pai
            tag (str): Nome da tag
            convert_type (type): Tipo para conversão (str, int, float, etc.)
            
        Returns:
            Valor convertido ou None se vazio
        """
        element = parent.find(tag)
        if element is not None and element.text:
            text = element.text.strip()
            if text:
                if convert_type == int:
                    return int(text)
                elif convert_type == float:
                    return float(text)
                return text
        return None
    
    def _format_price(self, preco: Optional[int]) -> Optional[str]:
        """
        Formata o preço para formato brasileiro
        
        Args:
            preco (Optional[int]): Preço em centavos
            
        Returns:
            Optional[str]: Preço formatado ou None
        """
        if preco is None:
            return None
        
        # Converte centavos para reais (remove 2 zeros)
        valor_reais = preco / 100
        return f"R$ {valor_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    def _parse_ano(self, ano: Optional[str]) -> tuple:
        """
        Separa ano de fabricação e modelo
        
        Args:
            ano (Optional[str]): String no formato "YYYY/YYYY"
            
        Returns:
            tuple: (ano_fabricacao, ano_modelo)
        """
        if not ano:
            return None, None
        
        if '/' in ano:
            partes = ano.split('/')
            return partes[0], partes[1]
        
        return ano, ano
    
    def to_json(self, indent: int = 2) -> str:
        """
        Converte os dados para JSON
        
        Args:
            indent (int): Indentação para formatação
            
        Returns:
            str: JSON formatado
        """
        if self.data is None:
            raise ValueError("Execute parse_xml() primeiro")
        
        return json.dumps(self.data, indent=indent, ensure_ascii=False)
    
    def save_json(self, output_file: str, indent: int = 2):
        """
        Salva os dados em um arquivo JSON
        
        Args:
            output_file (str): Caminho do arquivo de saída
            indent (int): Indentação para formatação
        """
        if self.data is None:
            raise ValueError("Execute parse_xml() primeiro")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_url(cls, url: str = None):
        """
        Método de conveniência para criar fetcher a partir de URL
        
        Args:
            url (str): URL do XML (usa XML_URL se None)
            
        Returns:
            XMLFetcher: Instância configurada para URL
        """
        return cls(url or XML_URL, is_url=True)
    
    @classmethod
    def from_file(cls, file_path: str):
        """
        Método de conveniência para criar fetcher a partir de arquivo
        
        Args:
            file_path (str): Caminho do arquivo XML
            
        Returns:
            XMLFetcher: Instância configurada para arquivo
        """
        return cls(file_path, is_url=False)
        """
        Retorna um resumo dos dados do estoque
        
        Returns:
            Dict: Resumo estatístico
        """
        if self.data is None:
            raise ValueError("Execute parse_xml() primeiro")
        
        veiculos = self.data['veiculos']
        
        # Contadores
        total_veiculos = len(veiculos)
        veiculos_com_preco = sum(1 for v in veiculos if v['preco'] is not None)
        veiculos_com_material = sum(1 for v in veiculos if v['temMaterialDivulgacao'])
        veiculos_com_checklist = sum(1 for v in veiculos if v['temChecklistPdf'])
        
        # Análise por cor
        cores = {}
        for veiculo in veiculos:
            cor = veiculo['cor']
            cores[cor] = cores.get(cor, 0) + 1
        
        # Análise por modelo (marca)
        modelos = {}
        for veiculo in veiculos:
            modelo = veiculo['modelo']
            if modelo:
                # Extrai a primeira palavra como "marca"
                marca = modelo.split()[0]
                modelos[marca] = modelos.get(marca, 0) + 1
        
        # Preços (apenas veículos com preço)
        precos = [v['preco'] for v in veiculos if v['preco'] is not None]
        
        return {
            'totalVeiculos': total_veiculos,
            'veiculosComPreco': veiculos_com_preco,
            'veiculosComMaterial': veiculos_com_material,
            'veiculosComChecklist': veiculos_com_checklist,
            'distribuicaoPorCor': cores,
            'distribuicaoPorMarca': modelos,
            'estatisticasPreco': {
                'menorPreco': min(precos) if precos else None,
                'maiorPreco': max(precos) if precos else None,
                'precoMedio': sum(precos) / len(precos) if precos else None,
                'totalVeiculosComPreco': len(precos)
            }
        }

# Exemplo de uso
if __name__ == "__main__":
    # Usando a URL configurada (padrão)
    fetcher = XMLFetcher()  # Usa XML_URL automaticamente
    
    # Ou especificando URL diferente
    # fetcher = XMLFetcher("https://outra-url.com/estoque.xml")
    
    # Ou usando arquivo local
    # fetcher = XMLFetcher.from_file('estoque_local.xml')
    
    try:
        # Faz o parse do XML
        print(f"Fonte: {fetcher.xml_source}")
        print(f"Tipo: {'URL' if fetcher.is_url else 'Arquivo local'}")
        print("Fazendo parse do XML...")
        
        data = fetcher.parse_xml()
        
        # Exibe resumo
        print("\n=== RESUMO DO ESTOQUE ===")
        summary = fetcher.get_summary()
        print(f"Total de veículos: {summary['totalVeiculos']}")
        print(f"Veículos com preço: {summary['veiculosComPreco']}")
        print(f"Veículos com material: {summary['veiculosComMaterial']}")
        print(f"Veículos com checklist: {summary['veiculosComChecklist']}")
        
        print("\nDistribuição por cor:")
        for cor, qtd in summary['distribuicaoPorCor'].items():
            print(f"  {cor}: {qtd}")
        
        print("\nDistribuição por marca:")
        for marca, qtd in summary['distribuicaoPorMarca'].items():
            print(f"  {marca}: {qtd}")
        
        # Salva em JSON
        print("\nSalvando em JSON...")
        fetcher.save_json('estoque.json')
        
        # Exemplo de acesso aos dados
        print("\n=== EXEMPLOS DE VEÍCULOS ===")
        for i, veiculo in enumerate(data['veiculos'][:3]):  # Primeiros 3 veículos
            print(f"\nVeículo {i+1}:")
            print(f"  Placa: {veiculo['placa']}")
            print(f"  Modelo: {veiculo['modelo']}")
            print(f"  Cor: {veiculo['cor']}")
            print(f"  Ano: {veiculo['ano']}")
            print(f"  KM: {veiculo['km']:,}".replace(',', '.') if veiculo['km'] else 'N/A')
            print(f"  Preço: {veiculo['precoFormatado'] or 'Não informado'}")
        
        print(f"\nArquivo JSON salvo como 'estoque.json'")
        print(f"Fonte: {data['fonte']}")
        print(f"Processado em: {data['dataProcessamento']}")
        
    except Exception as e:
        print(f"Erro: {e}")
        
        # Se erro com URL, sugere testar conectividade
        if fetcher.is_url:
            print("\nDicas para resolver:")
            print("1. Verifique se a URL está correta")
            print("2. Teste a URL no navegador")
            print("3. Verifique sua conexão com a internet")
            print(f"4. URL testada: {fetcher.xml_source}")
