"""
coletor.py - Coleta e Triagem de Vagas

Busca vagas novas no LinkedIn/Indeed via jobspy, avalia compatibilidade com a
IA, e se a nota for >= 75, salva a vaga como PENDENTE no banco vagas.db.
"""

import os
import csv
import sqlite3
import json
import time

from datetime import datetime
from jobspy import scrape_jobs

from motor_ia import avaliar_compatibilidade

DB_PATH = "vagas.db"
PERFIL_PATH = "perfil_base.json"
CONTATOS_PATH = "contatos_diretos.csv"
OUTPUT_DIR = "output"
NOTA_MINIMA = 75


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vagas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa TEXT,
            cargo TEXT,
            localizacao TEXT,
            url TEXT UNIQUE,
            descricao TEXT,
            compatibilidade INTEGER,
            status TEXT DEFAULT 'PENDENTE',
            data_coleta TEXT,
            cv_path TEXT,
            mensagem_apresentacao TEXT
        )
    """)
    conn.commit()
    conn.close()


def carregar_perfil():
    with open(PERFIL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def filtro_previo_valido(job: dict) -> bool:
    """
    Filtro preliminar 100% em Python puro (sem custo de IA):
    Garante que a vaga seja de psicologia e contenha descrição válida.
    """
    descricao = job.get("description", "") or ""
    if not descricao.strip():
        return False

    url = job.get("job_url", "")
    if not url:
        return False

    title = (job.get("title", "") or "").lower()
    
    # Palavras-chave obrigatórias para área de psicologia/saúde mental
    termos_chave = ["psicólog", "psicologia", "mental", "perito", "trânsito"]
    if not any(termo in title or termo in descricao.lower() for termo in termos_chave):
        return False

    return True


def buscar_vagas():
    init_db()
    perfil = carregar_perfil()

    print("Buscando lote ampliado de vagas no LinkedIn e Indeed (até 30 vagas)...")
    try:
        jobs = scrape_jobs(
            site_name=["linkedin", "indeed"],
            search_term="psicologo",
            location="Maceió, Alagoas, Brasil",
            results_wanted=30,
            hours_old=72,
        )
    except Exception as e:
        print(f"Erro ao buscar vagas via jobspy: {e}")
        return

    if jobs is None or len(jobs) == 0:
        print("Nenhuma vaga retornada pelo jobspy.")
        return

    conn = sqlite3.connect(DB_PATH)
    vagas_para_processar = []

    print(f"Aplicando filtro prévio em Python puro em {len(jobs)} vagas brutas...")
    for _, job in jobs.iterrows():
        job_dict = job.to_dict()
        
        # 1. Validação preliminar Python puro
        if not filtro_previo_valido(job_dict):
            continue

        url = job_dict.get("job_url", "")

        # 2. Verificação de duplicidade no Banco (UNIQUE URL)
        existente = conn.execute(
            "SELECT id FROM vagas WHERE url = ?", (url,)
        ).fetchone()
        if existente:
            continue

        vagas_para_processar.append(job_dict)

    conn.close()

    total_novas = len(vagas_para_processar)
    print(f"Vagas novas e aprovadas pelo filtro preliminar: {total_novas}")

    if total_novas == 0:
        print("Nenhuma vaga nova para processar.")
        return

    # 3. Processamento em Lotes (Blocos de 5) com Pausas de Segurança
    tamanho_lote = 5
    pausa_lote = 8
    novas_salvas = 0
    total_lotes = (total_novas + tamanho_lote - 1) // tamanho_lote

    conn = sqlite3.connect(DB_PATH)

    for i in range(0, total_novas, tamanho_lote):
        lote = vagas_para_processar[i:i + tamanho_lote]
        num_lote = (i // tamanho_lote) + 1
        print(f"\n--- Processando Lote {num_lote}/{total_lotes} ({len(lote)} vagas) ---")

        for job in lote:
            titulo = job.get("title", "")
            empresa = job.get("employer", "")
            descricao = job.get("description", "")
            url = job.get("job_url", "")
            localizacao = job.get("location", "")

            print(f"  Analisando com IA: {titulo} @ {empresa}...")
            score = avaliar_compatibilidade(descricao, perfil)
            print(f"    -> Compatibilidade: {score}/100")

            if score >= NOTA_MINIMA:
                try:
                    conn.execute(
                        """INSERT INTO vagas
                           (empresa, cargo, localizacao, url, descricao, compatibilidade,
                            status, data_coleta, cv_path, mensagem_apresentacao)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            empresa,
                            titulo,
                            localizacao,
                            url,
                            descricao,
                            score,
                            "PENDENTE",
                            datetime.now().isoformat(),
                            "",
                            "",
                        ),
                    )
                    conn.commit()
                    novas_salvas += 1
                    print(f"    [+] Vaga salva como PENDENTE!")
                except sqlite3.IntegrityError:
                    pass

        if num_lote < total_lotes:
            print(f"Pausando {pausa_lote} segundos para proteger o limite de cota (TPM) da IA...")
            time.sleep(pausa_lote)

    conn.close()
    print(f"\nColeta finalizada com sucesso! {novas_salvas} nova(s) vaga(s) salva(s) com nota >= {NOTA_MINIMA}.")


if __name__ == "__main__":
    buscar_vagas()

def carregar_contatos():
    contatos = []
    if os.path.exists(CONTATOS_PATH):
        with open(CONTATOS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                contatos.append(row)
    return contatos


def buscar_vagas():
    init_db()
    perfil = carregar_perfil()

    print("Buscando vagas no LinkedIn e Indeed...")
    jobs = scrape_jobs(
        site_name=["linkedin", "indeed"],
        search_term="psicologo",
        location="Brasil",
        results_wanted=20,
        hours_old=72,
    )

    conn = sqlite3.connect(DB_PATH)
    novas = 0

    for _, job in jobs.iterrows():
        descricao = job.get("description", "") or ""
        if not descricao.strip():
            continue

        url = job.get("job_url", "")
        if not url:
            continue

        existente = conn.execute(
            "SELECT id FROM vagas WHERE url = ?", (url,)
        ).fetchone()
        if existente:
            continue

        score = avaliar_compatibilidade(descricao, perfil)
        print(f"  {job.get('title', '')} @ {job.get('employer', '')} -> compatibilidade: {score}")

        if score >= NOTA_MINIMA:
            conn.execute(
                """INSERT INTO vagas
                   (empresa, cargo, localizacao, url, descricao, compatibilidade,
                    status, data_coleta, cv_path, mensagem_apresentacao)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.get("employer", ""),
                    job.get("title", ""),
                    job.get("location", ""),
                    url,
                    descricao,
                    score,
                    "PENDENTE",
                    datetime.now().isoformat(),
                    "",
                    "",
                ),
            )
            novas += 1

    conn.commit()
    conn.close()
    print(f"\nColeta finalizada: {novas} vaga(s) nova(s) com nota >= {NOTA_MINIMA}.")


if __name__ == "__main__":
    buscar_vagas()