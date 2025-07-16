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
UPDATE_INTERVAL_HOURS = 2
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
    
    # 1. Busca exata normalizada
    if search_normalized in model_normalized:
        return True
    
    # 2. Busca parcial com strings normalizadas
    if fuzz.partial_ratio(search_normalized, model_normalized) >= threshold:
        return True
    
    # 3. Busca com ordenação de tokens
    if fuzz.token_sort_ratio(search_normalized, model_normalized) >= threshold:
        return True
    
    # 4. Busca em palavras individuais (mais flexível)
    search_words = search_normalized.split()
    model_words = model_normalized.split()
    
    for search_word in search_words:
        for model_word in model_words:
            if search_word == model_word:
                return True
            if len(search_word) >= 2 and fuzz.ratio(search_word, model_word) >= 70:
                return True
            if len(search_word) >= 2 and search_word in model_word:
                return True
    
    # 5. Último recurso: busca muito flexível para casos como s-10 vs s10
    search_clean = ''.join(c for c in search_normalized if c.isalnum())
    model_clean = ''.join(c for c in model_normalized if c.isalnum())
    
    if len(search_clean) >= 2 and search_clean in model_clean:
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
        logger.info("Iniciando atualização dos dados...")
        
        fetcher = XMLFetcher()
        data = fetcher.parse_xml()
        fetcher.save_json(JSON_FILE_PATH)
        
        await load_vehicle_data()
        
        logger.info(f"Dados atualizados com sucesso: {len(data.get('veiculos', []))} veículos")
        logger.info(f"Fonte: {fetcher.xml_source}")
        
    except Exception as e:
        logger.error(f"Erro ao atualizar dados: {e}")
        logger.error(f"Verifique se a URL está configurada corretamente no xml_fetcher.py")

async def scheduler():
    """Scheduler para atualizar dados a cada 2 horas"""
    while True:
        try:
            await update_data_from_xml()
            await asyncio.sleep(UPDATE_INTERVAL_HOURS * 3600)
        except Exception as e:
            logger.error(f"Erro no scheduler: {e}")
            await asyncio.sleep(300)

@app.on_event("startup")
async def startup_event():
    """Inicialização da aplicação"""
    global scheduler_task
    
    await load_vehicle_data()
    
    if vehicle_data["data"] is None:
        await update_data_from_xml()
    
    scheduler_task = asyncio.create_task(scheduler())
    logger.info("Aplicação iniciada e scheduler ativo")

@app.on_event("shutdown")
async def shutdown_event():
    """Encerramento da aplicação"""
    global scheduler_task
    if scheduler_task:
        scheduler_task.cancel()
    logger.info("Aplicação encerrada")

@app.get("/")
async def root():
    """Endpoint raiz com informações da API"""
    return {
        "message": "API Estoque de Veículos",
        "version": "1.0.0",
        "last_update": vehicle_data["last_update"].isoformat() if vehicle_data["last_update"] else None,
        "total_vehicles": len(vehicle_data["data"]["veiculos"]) if vehicle_data["data"] else 0,
        "endpoints": {
            "vehicles": "/vehicles - Lista veículos com filtros",
            "vehicle": "/vehicles/{sequencia} - Busca por sequência",
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
    limit: Optional[int] = Query(50, description="Limite de resultados"),
    offset: Optional[int] = Query(0, description="Offset para paginação")
):
    """Busca veículos com filtros"""
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
        paginated_vehicles = filtered_vehicles[offset:offset + limit]
        
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
        "update_interval_hours": UPDATE_INTERVAL_HOURS,
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
        "json_file_exists": Path(JSON_FILE_PATH).exists()
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
