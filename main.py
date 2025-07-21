from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
import json
import asyncio
from datetime import datetime, timedelta
import logging
from pathlib import Path
from rapidfuzz import fuzz
import re
import uvicorn
from xml_fetcher import XMLFetcher

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
JSON_FILE_PATH = "estoque.json"
UPDATE_INTERVAL_MINUTES = 2  # Alterado para 2 minutos
FUZZY_THRESHOLD = 85

app = FastAPI(
    title="API Estoque de Veículos",
    description="API para consulta de estoque de veículos com busca fuzzy e filtros avançados",
    version="1.0.0"
)

# Variáveis globais para armazenar dados
vehicle_data = {"data": None, "last_update": None}
scheduler_task = None

# Mapeamento de cores flexível
COLOR_MAPPING = {
    "branco": ["branco", "branca", "white"],
    "preto": ["preto", "preta", "black"],
    "vermelho": ["vermelho", "vermelha", "red"],
    "azul": ["azul", "blue"],
    "prata": ["prata", "prata", "silver", "cinza", "gray"],
    "amarelo": ["amarelo", "amarela", "yellow"],
    "verde": ["verde", "green"],
    "bege": ["bege", "creme", "cream"],
    "dourado": ["dourado", "dourada", "gold"],
    "rosa": ["rosa", "pink"],
    "roxo": ["roxo", "roxa", "purple"],
    "marrom": ["marrom", "brown"]
}

def normalize_color(color_input: str) -> Optional[str]:
    """Normaliza a cor de entrada para a cor padrão do estoque"""
    if not color_input:
        return None
    
    color_lower = color_input.lower().strip()
    
    for standard_color, variations in COLOR_MAPPING.items():
        if color_lower in [v.lower() for v in variations]:
            return standard_color.upper()
    
    return color_input.upper()

def fuzzy_match_model(search_term: str, model: str, threshold: int = FUZZY_THRESHOLD) -> bool:
    """Verifica se o modelo corresponde ao termo de busca usando fuzzy matching"""
    if not search_term or not model:
        return True if not search_term else False
    
    def normalize_string(s):
        return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()
    
    search_normalized = normalize_string(search_term)
    model_normalized = normalize_string(model)
    
    # 1. BUSCA EXATA: Mais importante - deve ter prioridade
    if search_normalized in model_normalized:
        return True
    
    # 2. BUSCA POR PALAVRAS EXATAS: Cada palavra do search deve estar no modelo
    search_words = search_normalized.split()
    model_words = model_normalized.split()
    
    # Para buscas específicas como "s10", deve encontrar palavra similar
    if len(search_words) == 1:
        search_word = search_words[0]
        for model_word in model_words:
            # Busca exata na palavra
            if search_word == model_word:
                return True
            # Busca substring apenas se for bem específica
            if len(search_word) >= 3 and search_word in model_word:
                return True
            # Fuzzy apenas para palavras muito similares (>= 90%)
            if len(search_word) >= 3 and fuzz.ratio(search_word, model_word) >= 90:
                return True
    
    # 3. BUSCA MÚLTIPLAS PALAVRAS: Todas as palavras devem ter match
    else:
        matches = 0
        for search_word in search_words:
            word_found = False
            for model_word in model_words:
                if (search_word == model_word or 
                    (len(search_word) >= 3 and search_word in model_word) or
                    (len(search_word) >= 3 and fuzz.ratio(search_word, model_word) >= 85)):
                    word_found = True
                    break
            if word_found:
                matches += 1
        
        # Todas as palavras devem ter match
        if matches == len(search_words):
            return True
    
    # 4. ÚLTIMO RECURSO: Apenas para casos muito específicos como "s-10" vs "s10"
    search_clean = ''.join(c for c in search_normalized if c.isalnum())
    model_clean = ''.join(c for c in model_normalized if c.isalnum())
    
    # Deve ser match exato ou quase exato após limpeza
    if len(search_clean) >= 3:
        for model_word in model_words:
            model_word_clean = ''.join(c for c in model_word if c.isalnum())
            if search_clean == model_word_clean:
                return True
            # Apenas se for muito similar (>= 95%)
            if len(search_clean) >= 3 and fuzz.ratio(search_clean, model_word_clean) >= 95:
                return True
    
    return False

def fuzzy_match_year(search_term: str, year_field: str) -> bool:
    """Verifica se o ano corresponde ao termo de busca"""
    if not search_term or not year_field:
        return True if not search_term else False
    
    if search_term in year_field:
        return True
    
    return fuzz.partial_ratio(search_term, year_field) >= FUZZY_THRESHOLD

async def load_vehicle_data():
    """Carrega dados dos veículos do JSON"""
    global vehicle_data
    
    try:
        if Path(JSON_FILE_PATH).exists():
            with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                vehicle_data["data"] = data
                vehicle_data["last_update"] = datetime.now()
                logger.info(f"Dados carregados: {len(data.get('veiculos', []))} veículos")
        else:
            logger.warning(f"Arquivo {JSON_FILE_PATH} não encontrado")
            vehicle_data["data"] = None
    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}")
        vehicle_data["data"] = None

async def update_data_from_xml():
    """Atualiza os dados convertendo XML para JSON"""
    try:
        logger.info("🔄 Iniciando atualização automática dos dados...")
        
        fetcher = XMLFetcher()
        data = fetcher.parse_xml()
        fetcher.save_json(JSON_FILE_PATH)
        
        await load_vehicle_data()
        
        logger.info(f"✅ Dados atualizados com sucesso: {len(data.get('veiculos', []))} veículos")
        logger.info(f"📡 Fonte: {fetcher.xml_source}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar dados: {e}")
        logger.error(f"🔧 Verifique se a URL está configurada corretamente no xml_fetcher.py")

async def scheduler():
    """Scheduler para atualizar dados a cada 2 minutos"""
    while True:
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            logger.info(f"⏰ [{current_time}] Executando atualização automática do scheduler...")
            
            await update_data_from_xml()
            
            logger.info(f"⌛ Próxima atualização em {UPDATE_INTERVAL_MINUTES} minutos...")
            await asyncio.sleep(UPDATE_INTERVAL_MINUTES * 60)  # Convertido para segundos
            
        except Exception as e:
            logger.error(f"❌ Erro no scheduler: {e}")
            logger.info(f"🔄 Tentando novamente em 30 segundos...")
            await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    """Inicialização da aplicação"""
    global scheduler_task
    
    await load_vehicle_data()
    
    if vehicle_data["data"] is None:
        await update_data_from_xml()
    
    scheduler_task = asyncio.create_task(scheduler())
    logger.info(f"🚀 Aplicação iniciada e scheduler ativo (interval: {UPDATE_INTERVAL_MINUTES} minutos)")

@app.on_event("shutdown")
async def shutdown_event():
    """Encerramento da aplicação"""
    global scheduler_task
    if scheduler_task:
        scheduler_task.cancel()
    logger.info("🛑 Aplicação encerrada")

@app.get("/")
async def root():
    """Endpoint raiz com informações da API"""
    return {
        "message": "API Estoque de Veículos",
        "version": "1.0.0",
        "last_update": vehicle_data["last_update"].isoformat() if vehicle_data["last_update"] else None,
        "total_vehicles": len(vehicle_data["data"]["veiculos"]) if vehicle_data["data"] else 0,
        "scheduler_interval": f"{UPDATE_INTERVAL_MINUTES} minutos",
        "endpoints": {
            "vehicles": "/vehicles - Lista veículos com filtros (sem limite)",
            "vehicle": "/vehicles/{sequencia} - Busca por sequência",
            "catalogo": "/catalogo - Catálogo em texto: MODELO - ANO - KM",
            "summary": "/summary - Resumo do estoque",
            "update": "/update - Força atualização dos dados",
            "parametros": "placa, modelo, cor, ano, kmmax, valormax"
        }
    }

@app.get("/vehicles")
async def get_vehicles(
    placa: Optional[str] = Query(None, description="Placa do veículo"),
    modelo: Optional[str] = Query(None, description="Modelo (busca fuzzy)"),
    cor: Optional[str] = Query(None, description="Cor (aceita variações)"),
    ano: Optional[str] = Query(None, description="Ano (busca em 2020/2021 se buscar 2020)"),
    kmmax: Optional[int] = Query(None, description="KM máximo (cap de km)"),
    valormax: Optional[int] = Query(None, description="Valor máximo em reais (cap de preço)"),
    limit: Optional[int] = Query(None, description="Limite de resultados (opcional)"),
    offset: Optional[int] = Query(0, description="Offset para paginação")
):
    """Busca veículos com filtros - sem limite padrão de resultados"""
    try:
        if vehicle_data["data"] is None:
            raise HTTPException(status_code=503, detail="Dados não disponíveis")
        
        vehicles = vehicle_data["data"]["veiculos"]
        if not vehicles:
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "vehicles": []
            }
        
        filtered_vehicles = []
        
        normalized_color = None
        if cor:
            try:
                normalized_color = normalize_color(cor)
            except Exception as e:
                logger.warning(f"Erro ao normalizar cor '{cor}': {e}")
        
        for vehicle in vehicles:
            try:
                # Filtro por placa
                if placa and vehicle.get("placa"):
                    if placa.upper() not in vehicle["placa"].upper():
                        continue
                
                # Filtro por modelo
                if modelo:
                    if not fuzzy_match_model(modelo, vehicle.get("modelo", "")):
                        continue
                
                # Filtro por cor
                if normalized_color and vehicle.get("cor") != normalized_color:
                    continue
                
                # Filtro por ano
                if ano:
                    if not fuzzy_match_year(ano, vehicle.get("ano", "")):
                        continue
                
                # Filtro por KM máximo
                if kmmax is not None and vehicle.get("km") is not None:
                    if vehicle["km"] > kmmax:
                        continue
                
                # Filtro por valor máximo
                if valormax is not None and vehicle.get("preco") is not None:
                    if vehicle["preco"] > valormax:
                        continue
                
                filtered_vehicles.append(vehicle)
                
            except Exception as e:
                logger.error(f"Erro ao processar veículo {vehicle.get('sequencia', 'unknown')}: {e}")
                continue
        
        total = len(filtered_vehicles)
        
        # Aplicar paginação somente se limit for especificado
        if limit is not None:
            paginated_vehicles = filtered_vehicles[offset:offset + limit]
        else:
            # Se offset for especificado sem limit, aplicar apenas offset
            if offset > 0:
                paginated_vehicles = filtered_vehicles[offset:]
            else:
                paginated_vehicles = filtered_vehicles
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "vehicles": paginated_vehicles
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro interno na busca de veículos: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno do servidor: {str(e)}")

@app.get("/vehicles/{sequencia}")
async def get_vehicle_by_sequencia(sequencia: int):
    """Busca um veículo específico pela sequência"""
    try:
        if vehicle_data["data"] is None:
            raise HTTPException(status_code=503, detail="Dados não disponíveis")
        
        vehicles = vehicle_data["data"]["veiculos"]
        
        for vehicle in vehicles:
            if vehicle.get("sequencia") == sequencia:
                return vehicle
        
        raise HTTPException(status_code=404, detail="Veículo não encontrado")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar veículo {sequencia}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno do servidor: {str(e)}")

@app.get("/catalogo")
async def get_catalogo(
    modelo: Optional[str] = Query(None, description="Modelo (busca fuzzy)"),
    cor: Optional[str] = Query(None, description="Cor (aceita variações)"),
    ano: Optional[str] = Query(None, description="Ano"),
    kmmax: Optional[int] = Query(None, description="KM máximo"),
    valormax: Optional[int] = Query(None, description="Valor máximo em reais"),
    format: Optional[str] = Query("text", description="Formato de resposta: 'text' ou 'json'")
):
    """Retorna catálogo de veículos em formato texto, uma linha por veículo"""
    try:
        if vehicle_data["data"] is None:
            raise HTTPException(status_code=503, detail="Dados não disponíveis")
        
        vehicles = vehicle_data["data"]["veiculos"]
        if not vehicles:
            if format.lower() == "json":
                return {"total": 0, "vehicles": []}
            else:
                return "Nenhum veículo encontrado no estoque."
        
        filtered_vehicles = []
        
        # Aplicar os mesmos filtros do endpoint /vehicles
        normalized_color = None
        if cor:
            try:
                normalized_color = normalize_color(cor)
            except Exception as e:
                logger.warning(f"Erro ao normalizar cor '{cor}': {e}")
        
        for vehicle in vehicles:
            try:
                # Filtro por modelo
                if modelo:
                    if not fuzzy_match_model(modelo, vehicle.get("modelo", "")):
                        continue
                
                # Filtro por cor
                if normalized_color and vehicle.get("cor") != normalized_color:
                    continue
                
                # Filtro por ano
                if ano:
                    if not fuzzy_match_year(ano, vehicle.get("ano", "")):
                        continue
                
                # Filtro por KM máximo
                if kmmax is not None and vehicle.get("km") is not None:
                    if vehicle["km"] > kmmax:
                        continue
                
                # Filtro por valor máximo
                if valormax is not None and vehicle.get("preco") is not None:
                    if vehicle["preco"] > valormax:
                        continue
                
                filtered_vehicles.append(vehicle)
                
            except Exception as e:
                logger.error(f"Erro ao processar veículo {vehicle.get('sequencia', 'unknown')}: {e}")
                continue
        
        # Gerar as linhas do catálogo
        catalog_lines = []
        
        for vehicle in filtered_vehicles:
            modelo = vehicle.get("modelo", "MODELO NÃO INFORMADO")
            ano = vehicle.get("ano", "ANO NÃO INFORMADO")
            km = vehicle.get("km")
            
            # Formatar KM
            if km is not None:
                if km == 0:
                    km_formatted = "0 KM"
                else:
                    km_formatted = f"{km:,} KM".replace(",", ".")
            else:
                km_formatted = "KM NÃO INFORMADO"
            
            # Criar linha no formato: MODELO - ANO - KM
            line = f"{modelo} - {ano} - {km_formatted}"
            catalog_lines.append(line)
        
        if format.lower() == "json":
            return {
                "total": len(catalog_lines),
                "vehicles": catalog_lines
            }
        else:
            # Retornar como texto simples
            if not catalog_lines:
                return "Nenhum veículo encontrado com os filtros especificados."
            
            catalog_text = "\n".join(catalog_lines)
            
            # Adicionar cabeçalho com total
            header = f"CATÁLOGO DE VEÍCULOS ({len(catalog_lines)} veículos encontrados)\n"
            header += "=" * 50 + "\n\n"
            
            return header + catalog_text
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro interno no catálogo: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno do servidor: {str(e)}")

@app.get("/summary")
async def get_summary():
    """Retorna resumo estatístico do estoque"""
    try:
        if vehicle_data["data"] is None:
            raise HTTPException(status_code=503, detail="Dados não disponíveis")
        
        fetcher = XMLFetcher()
        fetcher.data = vehicle_data["data"]
        summary = fetcher.get_summary()
        
        summary["data_geracao"] = vehicle_data["data"].get("dataGeracao")
        summary["ultima_atualizacao"] = vehicle_data["last_update"].isoformat() if vehicle_data["last_update"] else None
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar resumo: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar resumo: {str(e)}")

@app.post("/update")
async def force_update(background_tasks: BackgroundTasks):
    """Força atualização dos dados do XML"""
    background_tasks.add_task(update_data_from_xml)
    return {"message": "Atualização iniciada em background"}

@app.get("/colors")
async def get_available_colors():
    """Retorna cores disponíveis e suas variações aceitas"""
    return {
        "color_mapping": COLOR_MAPPING,
        "description": "Você pode usar qualquer variação listada para cada cor"
    }

@app.get("/config")
async def get_config():
    """Retorna configurações atuais da API"""
    from xml_fetcher import XML_URL
    
    return {
        "xml_url": XML_URL,
        "update_interval_minutes": UPDATE_INTERVAL_MINUTES,
        "fuzzy_threshold": FUZZY_THRESHOLD,
        "json_output": JSON_FILE_PATH,
        "note": "Configure a URL no arquivo xml_fetcher.py"
    }

@app.get("/health")
async def health_check():
    """Verifica saúde da aplicação"""
    from xml_fetcher import XML_URL
    
    status = "healthy" if vehicle_data["data"] is not None else "unhealthy"
    
    return {
        "status": status,
        "last_update": vehicle_data["last_update"].isoformat() if vehicle_data["last_update"] else None,
        "total_vehicles": len(vehicle_data["data"]["veiculos"]) if vehicle_data["data"] else 0,
        "xml_url": XML_URL,
        "json_file_exists": Path(JSON_FILE_PATH).exists(),
        "scheduler_interval": f"{UPDATE_INTERVAL_MINUTES} minutos"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
