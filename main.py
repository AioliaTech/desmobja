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
