"""
painel.py - Controle Visual com Streamlit

Interface web local para revisar vagas pendentes, visualizar o PDF gerado,
editar a mensagem de apresentacao e escolher entre Aprovar e Enviar ou
Descartar.

Execute com:
    streamlit run painel.py
"""

import os
import json
import sqlite3
import smtplib
import re
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from motor_ia import adaptar_cv, gerar_pdf_playwright

from playwright.sync_api import sync_playwright

DB_PATH = "vagas.db"
PERFIL_PATH = "perfil_base.json"
CONTATOS_PATH = "contatos_diretos.csv"
OUTPUT_DIR = "output"
TEMPLATE_HTML = "template_cv.html"


# ---------------------------------------------------------------------------
# Helpers de banco de dados
# ---------------------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB_PATH)


def listar_pendentes():
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, empresa, cargo, localizacao, url, descricao, compatibilidade,
                  data_coleta, cv_path, mensagem_apresentacao
           FROM vagas WHERE status = 'PENDENTE'
           ORDER BY data_coleta DESC"""
    ).fetchall()
    conn.close()
    return rows


def atualizar_status(vaga_id, status, cv_path=None, mensagem=None):
    conn = get_conn()
    if cv_path is not None and mensagem is not None:
        conn.execute(
            "UPDATE vagas SET status = ?, cv_path = ?, mensagem_apresentacao = ? WHERE id = ?",
            (status, cv_path, mensagem, vaga_id),
        )
    elif cv_path is not None:
        conn.execute(
            "UPDATE vagas SET status = ?, cv_path = ? WHERE id = ?",
            (status, cv_path, vaga_id),
        )
    elif mensagem is not None:
        conn.execute(
            "UPDATE vagas SET status = ?, mensagem_apresentacao = ? WHERE id = ?",
            (status, mensagem, vaga_id),
        )
    else:
        conn.execute("UPDATE vagas SET status = ? WHERE id = ?", (status, vaga_id))
    conn.commit()
    conn.close()


def get_vaga(vaga_id):
    conn = get_conn()
    row = conn.execute(
        """SELECT id, empresa, cargo, localizacao, url, descricao, compatibilidade,
                  data_coleta, cv_path, mensagem_apresentacao
           FROM vagas WHERE id = ?""",
        (vaga_id,),
    ).fetchone()
    conn.close()
    return row


# ---------------------------------------------------------------------------
# Geracao de PDF com Playwright
# ---------------------------------------------------------------------------
def gerar_pdf(perfil_adaptado, empresa, output_dir=OUTPUT_DIR):
    """Gera um PDF ATS-friendly a partir do template HTML e dados adaptados."""
    os.makedirs(output_dir, exist_ok=True)

    template_path = Path(__file__).parent / TEMPLATE_HTML
    if not template_path.exists():
        template_path = Path(TEMPLATE_HTML)
    html = template_path.read_text(encoding="utf-8")

    html = html.replace("{{nome}}", perfil_adaptado.get("nome", ""))
    html = html.replace("{{titulo_profissional}}", perfil_adaptado.get("cargo", ""))
    html = html.replace("{{email}}", perfil_adaptado.get("email", ""))
    html = html.replace("{{telefone}}", perfil_adaptado.get("telefone", ""))
    html = html.replace("{{localizacao}}", perfil_adaptado.get("localizacao", ""))
    html = html.replace("{{linkedin}}", perfil_adaptado.get("linkedin", ""))
    html = html.replace("{{resumo_profissional}}", perfil_adaptado.get("resumo_profissional", ""))

    experiencias_html = ""
    for exp in perfil_adaptado.get("experiencias", []):
        experiencias_html += f"""
        <div class="experience-item">
            <h3>{exp.get('cargo', '')} <span class="company">{exp.get('empresa', '')}</span></h3>
            <div class="period">{exp.get('periodo', '')}</div>
            <p>{exp.get('descricao', '')}</p>
        </div>
        """
    html = re.sub(r"{% for exp in experiencias %}.*?{% endfor %}", experiencias_html, html, flags=re.DOTALL)

    habilidades_html = ""
    for hab in perfil_adaptado.get("habilidades", []):
        habilidades_html += f'<span class="skill-tag">{hab}</span>'
    html = re.sub(r"{% for hab in habilidades %}.*?{% endfor %}", habilidades_html, html, flags=re.DOTALL)

    educacao_html = ""
    for edu in perfil_adaptado.get("educacao", []):
        educacao_html += f"""
        <div class="education-item">
            <h3>{edu.get('curso', '')} <span class="inst">{edu.get('instituicao', '')}</span></h3>
            <div class="period">{edu.get('periodo', '')}</div>
        </div>
        """
    html = re.sub(r"{% for edu in educacao %}.*?{% endfor %}", educacao_html, html, flags=re.DOTALL)

    html = re.sub(r"{%.*?%}", "", html, flags=re.DOTALL)

    nome_arquivo = f"CV_{empresa.replace(' ', '_')}.pdf"
    caminho_pdf = os.path.join(output_dir, nome_arquivo)

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.set_content(html)
        pagina.pdf(path=caminho_pdf, format="A4", print_background=True)
        navegador.close()

    return caminho_pdf


# ---------------------------------------------------------------------------
# Envio de e-mail (Gmail SMTP)
# ---------------------------------------------------------------------------
def enviar_email(destinatario, assunto, corpo, anexo_path=None):
    """Envia e-mail via Gmail SMTP."""
    remetente = os.getenv("GMAIL_EMAIL")
    senha = os.getenv("GMAIL_APP_PASSWORD")

    if not remetente or not senha:
        raise RuntimeError("GMAIL_EMAIL e GMAIL_APP_PASSWORD nao configurados.")

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destinatario
    msg.set_content(corpo)

    if anexo_path and os.path.exists(anexo_path):
        with open(anexo_path, "rb") as f:
            dados = f.read()
        nome = os.path.basename(anexo_path)
        msg.add_attachment(dados, maintype="application", subtype="pdf", filename=nome)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(remetente, senha)
        smtp.send_message(msg)


# ---------------------------------------------------------------------------
# Interface Streamlit
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Painel de Vagas - Agente", page_icon="📄", layout="wide")

st.title("📄 Painel de Aprovacao de Vagas")
st.markdown("Revise as vagas pendentes, visualize o PDF gerado e decida o que fazer com cada uma.")

if os.path.exists(PERFIL_PATH):
    with open(PERFIL_PATH, "r", encoding="utf-8") as f:
        perfil = json.load(f)
else:
    perfil = {}
    st.warning("Arquivo perfil_base.json nao encontrado.")

pendentes = listar_pendentes()

if not pendentes:
    st.info("Nenhuma vaga pendente no momento. Execute o coletor.py para buscar novas vagas.")
else:
    st.subheader(f"Vagas Pendentes ({len(pendentes)})")

    for vaga in pendentes:
        (vaga_id, empresa, cargo, localizacao, url, descricao, compatibilidade,
         data_coleta, cv_path, mensagem_atual) = vaga

        with st.expander(f"{cargo} — {empresa} (Compatibilidade: {compatibilidade}/100)"):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**Empresa:** {empresa}")
                st.markdown(f"**Cargo:** {cargo}")
                st.markdown(f"**Localizacao:** {localizacao}")
                st.markdown(f"**URL:** {url}")
                st.markdown(f"**Data coleta:** {data_coleta}")
                st.markdown("**Descricao:**")
                st.text_area(
                    f"desc_{vaga_id}",
                    descricao[:2000] + ("..." if len(descricao) > 2000 else ""),
                    height=150,
                    disabled=True,
                    key=f"desc_{vaga_id}",
                )

            with col2:
                st.metric("Compatibilidade", f"{compatibilidade}/100")
                if cv_path and os.path.exists(cv_path):
                    st.success("PDF gerado")
                    with open(cv_path, "rb") as f:
                        st.download_button(
                            "Baixar PDF",
                            data=f.read(),
                            file_name=os.path.basename(cv_path),
                            mime="application/pdf",
                            key=f"dl_{vaga_id}",
                        )
                else:
                    st.warning("PDF nao gerado")

            nova_mensagem = st.text_area(
                "Mensagem de apresentacao",
                value=mensagem_atual or "",
                height=100,
                key=f"msg_{vaga_id}",
                placeholder="Escreva a mensagem que sera enviada ao recrutador...",
            )

            col_a, col_b, col_c = st.columns(3)

            with col_a:
                if st.button("Gerar PDF e Adaptar CV", key=f"gen_{vaga_id}"):
                    with st.spinner("Adaptando CV e gerando PDF..."):
                        try:
                            palavras_chave = extrair_palavras_chave(descricao)
                            perfil_adaptado = adaptar_cv(perfil, descricao, palavras_chave)
                            caminho_pdf = gerar_pdf(perfil_adaptado, empresa)
                            atualizar_status(vaga_id, "PENDENTE", cv_path=caminho_pdf)
                            st.success(f"PDF gerado: {caminho_pdf}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao gerar PDF: {e}")

            with col_b:
                if st.button("Aprovar e Enviar", key=f"aprovar_{vaga_id}", type="primary"):
                    contato_email = ""
                    if os.path.exists(CONTATOS_PATH):
                        import csv
                        with open(CONTATOS_PATH, "r", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get("empresa", "").lower() == empresa.lower():
                                    contato_email = row.get("email", "")
                                    break

                    assunto = f"Candidatura: {cargo} - {perfil.get('nome', '')}"
                    corpo = nova_mensagem or f"Prezado time de recrutamento da {empresa},\n\nGostaria de me candidatar a vaga de {cargo}. Anexo meu CV adaptado.\n\nAtenciosamente,\n{perfil.get('nome', '')}"

                    try:
                        if contato_email:
                            enviar_email(contato_email, assunto, corpo, anexo_path=cv_path)
                            atualizar_status(vaga_id, "ENVIADO", mensagem=nova_mensagem)
                            st.success(f"E-mail enviado para {contato_email}!")
                        else:
                            st.warning("Nenhum email de contato encontrado para esta empresa.")
                    except Exception as e:
                        st.error(f"Falha ao enviar e-mail: {e}")
                        if st.button("Abrir link da vaga no navegador", key=f"link_{vaga_id}"):
                            import webbrowser
                            webbrowser.open(url)
                            atualizar_status(vaga_id, "ENVIADO", mensagem=nova_mensagem)
                            st.info("Link aberto no navegador. Finalize a candidatura manualmente.")
                            st.rerun()

            with col_c:
                if st.button("Descartar", key=f"descartar_{vaga_id}"):
                    atualizar_status(vaga_id, "DESCARTADO")
                    st.info("Vaga descartada.")
                    st.rerun()

st.divider()
st.caption("Agente Vagas — coletor.py | motor_ia.py (LiteLLM) | painel.py (Streamlit)")