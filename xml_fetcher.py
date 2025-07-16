import xml.etree.ElementTree as ET
import json
from datetime import datetime
from typing import Dict, List, Optional

class XMLFetcher:
    def __init__(self, xml_file_path: str):
        """
        Inicializa o XMLFetcher com o caminho do arquivo XML
        
        Args:
            xml_file_path (str): Caminho para o arquivo XML
        """
        self.xml_file_path = xml_file_path
        self.data = None
    
    def parse_xml(self) -> Dict:
        """
        Faz o parse do XML e converte para um dicionário Python
        
        Returns:
            Dict: Dados do estoque em formato de dicionário
        """
        try:
            # Carrega e faz parse do XML
            tree = ET.parse(self.xml_file_path)
            root = tree.getroot()
            
            # Extrai informações gerais do estoque
            estoque_data = {
                'dataGeracao': self._get_element_text(root, 'dataGeracao'),
                'totalVeiculos': self._get_element_text(root, 'totalVeiculos', int),
                'veiculos': []
            }
            
            # Processa cada veículo
            veiculos_element = root.find('veiculos')
            if veiculos_element is not None:
                for veiculo in veiculos_element.findall('veiculo'):
                    veiculo_data = self._parse_veiculo(veiculo)
                    estoque_data['veiculos'].append(veiculo_data)
            
            self.data = estoque_data
            return estoque_data
            
        except ET.ParseError as e:
            raise ValueError(f"Erro ao fazer parse do XML: {e}")
        except FileNotFoundError:
            raise FileNotFoundError(f"Arquivo XML não encontrado: {self.xml_file_path}")
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
        
        # Adiciona campos derivados para facilitar análises
        veiculo_data['precoFormatado'] = self._format_price(veiculo_data['preco'])
        veiculo_data['anoFabricacao'], veiculo_data['anoModelo'] = self._parse_ano(veiculo_data['ano'])
        veiculo_data['temMaterialDivulgacao'] = bool(veiculo_data['linkMaterialDivulgacao'])
        veiculo_data['temChecklistPdf'] = bool(veiculo_data['checklistPdf'])
        
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
        
        # Converte centavos para reais
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
    
    def get_summary(self) -> Dict:
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
    # Inicializa o fetcher
    fetcher = XMLFetcher('estoque.xml')
    
    try:
        # Faz o parse do XML
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
        
    except Exception as e:
        print(f"Erro: {e}")
