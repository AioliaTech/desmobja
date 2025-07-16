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
XML_FILE_PATH = "estoque.xml"
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
    """
    Normaliza a cor de entrada para a cor padrão do estoque
    
    Args:
        color_input (str): Cor fornecida pelo usuário
        
    Returns:
        Optional[str]: Cor normalizada ou None se não encontrada
    """
    if not color_input:
        return None
    
    color_lower = color_input.lower().strip()
    
    for standard_color, variations in COLOR_MAPPING.items():
        if color_lower in [v.lower() for v in variations]:
            return standard_color.upper()  # Retorna no formato do XML (maiúsculo)
    
    return color_input.upper()  # Se não encontrar, retorna em maiúsculo

def fuzzy_match_model(search_term: str, model: str, threshold: int = FUZZY_THRESHOLD) -> bool:
    """
    Verifica se o modelo corresponde ao termo de busca usando fuzzy matching
    
    Args:
        search_term (str): Termo de busca
        model (str): Modelo do veículo
        threshold (int): Limiar de similaridade (0-100)
        
    Returns:
        bool: True se a similaridade for >= threshold
    """
    if not search_term or not model:
        return True if not search_term else False
    
    search_lower = search_term.lower()
    model_lower = model.lower()
    
    # 1. Busca parcial (melhor para substrings)
    if fuzz.partial_ratio(search_lower, model_lower) >= threshold:
        return True
    
    # 2. Busca com ordenação de tokens (melhor para palavras fora de ordem)
    if fuzz.token_sort_ratio(search_lower, model_lower) >= threshold:
        return True
    
    # 3. Busca em palavras individuais
    search_words = search_lower.split()
    model_words = model_lower.split()
    
    for search_word in search_words:
        for model_word in model_words:
            # Ratio simples para palavras exatas
            if fuzz.ratio(search_word, model_word) >= threshold:
                return True
            # Ratio parcial para substrings em palavras
            if len(search_word) >= 3 and fuzz.partial_ratio(search_word, model_word) >= threshold:
                return True
    
    return False

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
        
        if not Path(XML_FILE_PATH).exists():
            logger.error(f"Arquivo XML não encontrado: {XML_FILE_PATH}")
            return
        
        # Usa o XMLFetcher para converter XML para JSON
        fetcher = XMLFetcher(XML_FILE_PATH)
        data = fetcher.parse_xml()
        fetcher.save_json(JSON_FILE_PATH)
        
        # Recarrega os dados
        await load_vehicle_data()
        
        logger.info(f"Dados atualizados com sucesso: {len(data.get('veiculos', []))} veículos")
        
    except Exception as e:
        logger.error(f"Erro ao atualizar dados: {e}")

async def scheduler():
    """Scheduler para atualizar dados a cada 2 horas"""
    while True:
        try:
            await update_data_from_xml()
            await asyncio.sleep(UPDATE_INTERVAL_HOURS * 3600)  # 2 horas em segundos
        except Exception as e:
            logger.error(f"Erro no scheduler: {e}")
            await asyncio.sleep(300)  # Aguarda 5 minutos antes de tentar novamente

@app.on_event("startup")
async def startup_event():
    """Inicialização da aplicação"""
    global scheduler_task
    
    # Carrega dados iniciais
    await load_vehicle_data()
    
    # Se não tiver dados, tenta atualizar do XML
    if vehicle_data["data"] is None:
        await update_data_from_xml()
    
    # Inicia o scheduler
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
            "update": "/update - Força atualização dos dados"
        }
    }

@app.get("/vehicles")
async def get_vehicles(
    sequencia: Optional[int] = Query(None, description="Sequência do veículo"),
    placa: Optional[str] = Query(None, description="Placa do veículo"),
    modelo: Optional[str] = Query(None, description="Modelo (busca fuzzy com 85% similaridade)"),
    cor: Optional[str] = Query(None, description="Cor (aceita variações: branco/branca, vermelho/vermelha)"),
    ano_fabricacao: Optional[str] = Query(None, description="Ano de fabricação"),
    ano_modelo: Optional[str] = Query(None, description="Ano do modelo"),
    km_min: Optional[int] = Query(None, description="Quilometragem mínima"),
    km_max: Optional[int] = Query(None, description="Quilometragem máxima"),
    preco_min: Optional[int] = Query(None, description="Preço mínimo (em centavos)"),
    preco_max: Optional[int] = Query(None, description="Preço máximo (em centavos)"),
    tem_preco: Optional[bool] = Query(None, description="Filtrar apenas veículos com preço"),
    tem_material: Optional[bool] = Query(None, description="Filtrar apenas veículos com material de divulgação"),
    tem_checklist: Optional[bool] = Query(None, description="Filtrar apenas veículos com checklist PDF"),
    limit: Optional[int] = Query(50, description="Limite de resultados"),
    offset: Optional[int] = Query(0, description="Offset para paginação")
):
    """
    Busca veículos com filtros avançados
    
    - **modelo**: Busca fuzzy com 85% de similaridade
    - **cor**: Aceita variações (branco/branca, vermelho/vermelha, etc.)
    - **precos**: Em centavos (ex: 5000000 = R$ 50.000,00)
    """
    if vehicle_data["data"] is None:
        raise HTTPException(status_code=503, detail="Dados não disponíveis")
    
    vehicles = vehicle_data["data"]["veiculos"]
    filtered_vehicles = []
    
    # Normaliza cor se fornecida
    normalized_color = normalize_color(cor) if cor else None
    
    for vehicle in vehicles:
        # Aplica filtros
        if sequencia is not None and vehicle.get("sequencia") != sequencia:
            continue
        
        if placa and vehicle.get("placa") and placa.upper() not in vehicle["placa"].upper():
            continue
        
        if modelo and not fuzzy_match_model(modelo, vehicle.get("modelo", "")):
            continue
        
        if normalized_color and vehicle.get("cor") != normalized_color:
            continue
        
        if ano_fabricacao and vehicle.get("anoFabricacao") != ano_fabricacao:
            continue
        
        if ano_modelo and vehicle.get("anoModelo") != ano_modelo:
            continue
        
        if km_min is not None and (vehicle.get("km") is None or vehicle["km"] < km_min):
            continue
        
        if km_max is not None and (vehicle.get("km") is None or vehicle["km"] > km_max):
            continue
        
        if preco_min is not None and (vehicle.get("preco") is None or vehicle["preco"] < preco_min):
            continue
        
        if preco_max is not None and (vehicle.get("preco") is None or vehicle["preco"] > preco_max):
            continue
        
        if tem_preco is not None and bool(vehicle.get("preco")) != tem_preco:
            continue
        
        if tem_material is not None and vehicle.get("temMaterialDivulgacao") != tem_material:
            continue
        
        if tem_checklist is not None and vehicle.get("temChecklistPdf") != tem_checklist:
            continue
        
        filtered_vehicles.append(vehicle)
    
    # Aplica paginação
    total = len(filtered_vehicles)
    paginated_vehicles = filtered_vehicles[offset:offset + limit]
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "vehicles": paginated_vehicles,
        "filters_applied": {
            "sequencia": sequencia,
            "placa": placa,
            "modelo": modelo,
            "cor_original": cor,
            "cor_normalizada": normalized_color,
            "ano_fabricacao": ano_fabricacao,
            "ano_modelo": ano_modelo,
            "km_range": f"{km_min}-{km_max}" if km_min or km_max else None,
            "preco_range": f"{preco_min}-{preco_max}" if preco_min or preco_max else None,
            "tem_preco": tem_preco,
            "tem_material": tem_material,
            "tem_checklist": tem_checklist
        }
    }

@app.get("/vehicles/{sequencia}")
async def get_vehicle_by_sequencia(sequencia: int):
    """Busca um veículo específico pela sequência"""
    if vehicle_data["data"] is None:
        raise HTTPException(status_code=503, detail="Dados não disponíveis")
    
    vehicles = vehicle_data["data"]["veiculos"]
    
    for vehicle in vehicles:
        if vehicle.get("sequencia") == sequencia:
            return vehicle
    
    raise HTTPException(status_code=404, detail="Veículo não encontrado")

@app.get("/summary")
async def get_summary():
    """Retorna resumo estatístico do estoque"""
    if vehicle_data["data"] is None:
        raise HTTPException(status_code=503, detail="Dados não disponíveis")
    
    try:
        # Usa o XMLFetcher para gerar o resumo
        fetcher = XMLFetcher(XML_FILE_PATH)
        fetcher.data = vehicle_data["data"]  # Usa dados já carregados
        summary = fetcher.get_summary()
        
        # Adiciona informações de atualização
        summary["data_geracao"] = vehicle_data["data"].get("dataGeracao")
        summary["ultima_atualizacao"] = vehicle_data["last_update"].isoformat() if vehicle_data["last_update"] else None
        
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar resumo: {e}")

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

@app.get("/health")
async def health_check():
    """Verifica saúde da aplicação"""
    status = "healthy" if vehicle_data["data"] is not None else "unhealthy"
    
    return {
        "status": status,
        "last_update": vehicle_data["last_update"].isoformat() if vehicle_data["last_update"] else None,
        "total_vehicles": len(vehicle_data["data"]["veiculos"]) if vehicle_data["data"] else 0,
        "xml_file_exists": Path(XML_FILE_PATH).exists(),
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
