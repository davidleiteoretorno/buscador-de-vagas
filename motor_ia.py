"""
motor_ia.py - Motor de Inteligência Artificial com Conexão Direta (Groq, OpenRouter, Gemini)
Elimina o LiteLLM e conecta diretamente às APIs gratuitas com sistema de Fallback automático.
"""

import os
import json
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")


def truncar_descricao(descricao: str, limite: int = 1200) -> str:
    """Trunca a descrição da vaga estritamente para o limite de caracteres especificado."""
    if not descricao:
        return ""
    return descricao[:limite]


def chamada_groq(prompt: str) -> str:
    """Chama a API da Groq (Llama 3 8B)."""
    if not GROQ_KEY:
        raise ValueError("GROQ_API_KEY não configurada.")
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 500
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Erro Groq ({response.status_code}): {response.text}")
    
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def chamada_openrouter(prompt: str) -> str:
    """Chama a API do OpenRouter (modelo free)."""
    if not OPENROUTER_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurada.")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/agente-vagas",
        "X-Title": "Agente Vagas"
    }
    payload = {
        "model": "meta-llama/llama-3-8b-instruct:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 500
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Erro OpenRouter ({response.status_code}): {response.text}")
    
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def chamada_gemini(prompt: str) -> str:
    """Chama a API do Google Gemini diretamente via REST."""
    if not GEMINI_KEY:
        raise ValueError("GEMINI_API_KEY não configurada.")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Erro Gemini ({response.status_code}): {response.text}")
    
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Resposta inesperada do Gemini: {data}") from e


def executar_ia_com_fallback(prompt: str) -> str:
    """
    Tenta executar a IA usando Groq -> OpenRouter -> Gemini em sequência (Fallback automático).
    """
    erros = []

    # 1. Tentativa Groq (Mais rápida)
    try:
        return chamada_groq(prompt)
    except Exception as e:
        erros.append(f"Groq: {e}")

    # 2. Tentativa OpenRouter
    try:
        return chamada_openrouter(prompt)
    except Exception as e:
        erros.append(f"OpenRouter: {e}")

    # 3. Tentativa Gemini
    try:
        return chamada_gemini(prompt)
    except Exception as e:
        erros.append(f"Gemini: {e}")

    raise RuntimeError(f"Todas as tentativas de IA falharam. Erros: {'; '.join(erros)}")
def avaliar_compatibilidade(descricao: str, perfil: dict) -> int:
    """
    Realiza a triagem e avaliação de compatibilidade da vaga com o perfil,
    limitando a descrição estritamente a 1.200 caracteres.
    Retorna um inteiro de 0 a 100 representando a nota de compatibilidade.
    """
    descricao_truncada = truncar_descricao(descricao, 1200)

    prompt = f"""
Você é um recrutador especialista e consultor de carreira.
Analise a descrição da vaga abaixo e o perfil profissional do candidato.
Atribua uma nota de 0 a 100 indicando o nível de compatibilidade do candidato com a vaga.
Responda APENAS com um número inteiro (ex: 85). Nenhuma outra palavra ou explicação.

Perfil do Candidato:
{json.dumps(perfil, ensure_ascii=False, indent=2)}

Descrição da Vaga:
{descricao_truncada}
"""

    try:
        resposta_texto = executar_ia_com_fallback(prompt)
        digitos = "".join(filter(str.isdigit, resposta_texto))
        return int(digitos) if digitos else 0
    except Exception as e:
        print(f"Erro ao avaliar compatibilidade com IA: {e}")
        return 0


def adaptar_cv(descricao: str, perfil: dict) -> dict:
    """
    Adapta o currículo e gera uma mensagem de apresentação personalizada
    com base na descrição da vaga e no perfil base.
    """
    descricao_truncada = truncar_descricao(descricao, 1200)

    prompt = f"""
Com base na descrição da vaga e no perfil profissional do candidato abaixo, retorne um objeto JSON contendo exatamente duas chaves:
1. "cv_adaptado": Um texto formatado ou markdown com o currículo adaptado e otimizado para destacar as competências mais relevantes para esta vaga específica.
2. "mensagem_apresentacao": Uma mensagem de apresentação profissional (cover letter / mensagem para o recrutador) persuasiva e objetiva.

Retorne APENAS o JSON válido, sem blocos de código markdown adicionais (como ```json ... ```), apenas o objeto JSON puro.

Perfil Base:
{json.dumps(perfil, ensure_ascii=False, indent=2)}

Descrição da Vaga:
{descricao_truncada}
"""

    try:
        conteudo = executar_ia_com_fallback(prompt)
        
        # Limpeza caso venha em bloco markdown
        if conteudo.startswith("```"):
            conteudo = conteudo.split("```")[1]
            if conteudo.startswith("json"):
                conteudo = conteudo[4:]
            conteudo = conteudo.strip()
            if conteudo.endswith("```"):
                conteudo = conteudo[:-3].strip()

        dados = json.loads(conteudo)
        return {
            "cv_adaptado": dados.get("cv_adaptado", ""),
            "mensagem_apresentacao": dados.get("mensagem_apresentacao", "")
        }
    except Exception as e:
        print(f"Erro ao adaptar CV com IA: {e}")
        return {
            "cv_adaptado": perfil.get("resumo_profissional", ""),
            "mensagem_apresentacao": "Olá, tenho interesse na vaga e gostaria de apresentar minha candidatura."
        }


def gerar_pdf_playwright(html_content: str, output_path: str):
    """
    Gera um arquivo PDF a partir de conteúdo HTML utilizando o Playwright.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        page.pdf(path=output_path, format="A4", print_background=True)
        browser.close()




def avaliar_compatibilidade(descricao: str, perfil: dict) -> int:
    """
    Realiza a triagem e avaliação de compatibilidade da vaga com o perfil,
    limitando a descrição estritamente a 1.200 caracteres.
    Retorna um inteiro de 0 a 100 representando a nota de compatibilidade.
    """
    descricao_truncada = truncar_descricao(descricao, 1200)

    prompt = f"""
Você é um recrutador especialista e consultor de carreira.
Analise a descrição da vaga abaixo e o perfil profissional do candidato.
Atribua uma nota de 0 a 100 indicando o nível de compatibilidade do candidato com a vaga.
Responda APENAS com um número inteiro (ex: 85). Nenhuma outra palavra ou explicação.

Perfil do Candidato:
{json.dumps(perfil, ensure_ascii=False, indent=2)}

Descrição da Vaga:
{descricao_truncada}
"""

    try:
        response = completion(
            model=MODELO_IA,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0
        )
        resposta_texto = response.choices[0].message.content.strip()
        # Remove qualquer caractere não numérico caso o modelo retorne algo a mais
        digitos = "".join(filter(str.isdigit, resposta_texto))
        return int(digitos) if digitos else 0
    except Exception as e:
        print(f"Erro ao avaliar compatibilidade com IA: {e}")
        return 0


def adaptar_cv(descricao: str, perfil: dict) -> dict:
    """
    Adapta o currículo e gera uma mensagem de apresentação personalizada
    com base na descrição da vaga e no perfil base.
    """
    descricao_truncada = truncar_descricao(descricao, 1200)

    prompt = f"""
Com base na descrição da vaga e no perfil profissional do candidato abaixo, retorne um objeto JSON contendo exatamente duas chaves:
1. "cv_adaptado": Um texto formatado ou markdown com o currículo adaptado e otimizado para destacar as competências mais relevantes para esta vaga específica.
2. "mensagem_apresentacao": Uma mensagem de apresentação profissional (cover letter / mensagem para o recrutador) persuasiva e objetiva.

Retorne APENAS o JSON válido, sem blocos de código markdown adicionais (como ```json ... ```), apenas o objeto JSON puro.

Perfil Base:
{json.dumps(perfil, ensure_ascii=False, indent=2)}

Descrição da Vaga:
{descricao_truncada}
"""

    try:
        response = completion(
            model=MODELO_IA,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        conteudo = response.choices[0].message.content.strip()
        
        # Limpeza caso venha em bloco markdown
        if conteudo.startswith("```"):
            conteudo = conteudo.split("```")[1]
            if conteudo.startswith("json"):
                conteudo = conteudo[4:]
            conteudo = conteudo.strip()
            if conteudo.endswith("```"):
                conteudo = conteudo[:-3].strip()

        dados = json.loads(conteudo)
        return {
            "cv_adaptado": dados.get("cv_adaptado", ""),
            "mensagem_apresentacao": dados.get("mensagem_apresentacao", "")
        }
    except Exception as e:
        print(f"Erro ao adaptar CV com IA: {e}")
        return {
            "cv_adaptado": perfil.get("resumo_profissional", ""),
            "mensagem_apresentacao": "Olá, tenho interesse na vaga e gostaria de apresentar minha candidatura."
        }


def gerar_pdf_playwright(html_content: str, output_path: str):
    """
    Gera um arquivo PDF a partir de conteúdo HTML utilizando o Playwright.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        page.pdf(path=output_path, format="A4", print_background=True)
        browser.close()
