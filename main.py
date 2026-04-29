import os
from dotenv import load_dotenv
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
#import google.generativeai as genai
from openai import OpenAI


#from google.generativeai.types import GenerationConfig
import json

from supabase import create_client, Client
load_dotenv()
#genai.configure(api_key="AIzaSyDvsw02McFgaApkHyJy0y16f9q8aFsarq0")

#model = genai.GenerativeModel('gemini-2.5-flash')
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------------------------------#
# Base dos elementos 
# -------------------------------------

class EstrategiaRevisao(ABC):
    @abstractmethod
    def calculo_proxima(self, card, nota: int):
        pass

class AlgoritmoRepEspacada(EstrategiaRevisao):
    def calculo_proxima(self, card, nota:int):
        if nota >= 3:
            intervalo_novo = max(1, round(card.intervalo * 2.5))
        else:
            intervalo_novo = 0
        return datetime.now() + timedelta(days=intervalo_novo), intervalo_novo
        
class AlgoritmoIA(EstrategiaRevisao):
    def calculo_proxima(self, card, nota: int):
        if nota >= 3:
            intervalo_novo = max(1, round(card.intervalo * 1.5))
        else: 
            intervalo_novo = 0
        return datetime.now() + timedelta(days=intervalo_novo), intervalo_novo

# Classes Basicas - Pilares    
class BaseCard(ABC):
    def __init__(self, frente, verso, estrategia: EstrategiaRevisao):
        self.frente = frente
        self.verso = verso
        self.intervalo = 0
        self.estrategia = estrategia
    
    def revisao(self, nota: int):
        data_proxima, self.intervalo = self.estrategia.calculo_proxima(self, nota)
        return data_proxima

class Cardmanual(BaseCard):
    def __init__(self, frente, verso, estrategia, anexo=None):
        super().__init__(frente, verso, estrategia)
        self.anexo = anexo
        
class CardIA(BaseCard):
    def __init__(self, frente, verso, estrategia, contexto):
        super().__init__(frente, verso, estrategia)
        self.contexto = contexto
     

app = FastAPI(title = "Api EasyCards")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReqRevisao(BaseModel):
    nota: int
    frente: str
    verso: str
    
@app.get("/")
def home():
        return {"mensagem": "API rodando em arquivo unico"}
    
@app.post("/revisar-card")
def simular_revisao(req: ReqRevisao):
        meu_algoritmo = AlgoritmoRepEspacada()
        card_atual = Cardmanual(req.frente, req.verso, meu_algoritmo)
        proxima_data = card_atual.revisao(req.nota)
        
        return {
            "status": "sucesso",
            "frente": card_atual.frente,
            "novo_intervalo(dias)": card_atual.intervalo,
            "proxima_revisao": proxima_data.strftime("%Y-%m-%d %H: %M:%S")
            
        }
        
@app.post("/popular-banco-teste")
def popular_banco():
    resposta_deck = supabase.table("decks").insert({"nome": "Estudos Biologia"}).execute()
    
    deck_id = resposta_deck.data[0]['id'] #identificar o id gerdo pelo banco para o deck
    resposta_card = supabase.table("flashcards").insert({
        "deck_id": deck_id,
        "frente": "Qual parte do corpo é considerada o segundo coração?",
        "verso": "É a panturrilha",
        "tipo": "manual"
        }).execute()    
    
    return{
        "status": "sucesso",
        "mensagem": "Deck e card salvos na nuvem banco de dados",
        "card_salvo": resposta_card.data[0]
    }
    
    
class ReqGeracao_IA(BaseModel):
        texto_contexto: str
        
@app.post("/gerar-cards-ia")
def gerar_cards_comIA(req:ReqGeracao_IA):
    
    #model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Atue como assistente de estudos, com foco na criação de flashcards. Leia o texto abaixo e extraia os três conceitos mais importantes e formate-os como perguntas e respostas sucintas.
    Retorne somente um JSON válido no seguinte formato de lista, sem explicações extras e sem blocos de código markdown (```json):
    [
        {{"frente": "pergunta", "verso": "resposta"}}
    ]
    
    Texto: {req.texto_contexto}
    """
    '''
    try:
        response = model.generate_content(prompt)
        texto_limpeza = response.text.replace("```json", "").replace("```", "").strip()
        cards_gerados = json.loads(texto_limpeza)
        '''
    try: 
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Você é um assistente que gera apenas JSON puro."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3 # Mantém a IA focada e menos criativa (ideal para JSON)
        )
        texto_resposta = response.choices[0].message.content
        texto_limpeza = texto_resposta.replace("```json", "").replace("```", "").strip()
        cards_gerados = json.loads(texto_limpeza)
        return{
            "status": "sucesso",
            "quantidade": len(cards_gerados),
            "cards": cards_gerados
        }
    except Exception as e:
        return{ "erro": "erro no processamento de IA", "detalhes": str(e)}
    

class ListaCardsIA(BaseModel):
    deck_id: str
    cards: list
    
@app.post("/salvar-cards-ia")
def salvar_cards_ia(req: ListaCardsIA):
    try: #preparar os dados para o formato do banco
        dados_pra_banco = []
        for card in req.cards:
            dados_pra_banco.append({
                "deck_id": req.deck_id,
                "frente": card['frente'],
                "verso": card['verso'],
                "tipo": "IA"
            })
        resposta = supabase.table("flashcards").insert(dados_pra_banco).execute()
        return {"status": "sucesso", "mensagem": f"{len(req.cards)} cards salvos corretamente"}
    except Exception as e:
        return { "status": "falhou", "detalhes": str(e)}
    
    
# Rota para pegar cards a serem revisados goje
@app.get("/cards-para-revisar/{user_id}")
def buscar_cards_revisao(user_id: str):
    try:
        from datetime import datetime
        agora = datetime.now().isoformat()
        
        resposta = supabase.table("flashcards")\
        .select("*")\
        .eq("user_id", user_id)\
        .lte("proxima_revisao", agora)\
        .execute()
        return {"status": "sucesso", "cards": resposta.data}
    except Exception as e:
        return { "status": "erro"}

# Receber a nota e aplicar logica junto ao banco de dados

class ReqProcessoRevisao(BaseModel):
    card_id: str
    nota: int
    
@app.post("/processo-revisao")
def processo_revisao(req: ReqProcessoRevisao):
    
    res = supabase.table("flashcards").select("*").eq("id", req.card_id).single().execute()
    dados = res.data #Buscando ocard atual dentro do banco de dados

    if dados.get('tipo') == 'IA':
        algoritmo = AlgoritmoIA()
    else:
        algoritmo = AlgoritmoRepEspacada()
        
    
    erros_atuais = dados.get('erros_consecutivos', 0)
    if req.nota < 3:
        novos_erros = erros_atuais + 1
    else:
        novos_erros = 0
   # algoritmo = AlgoritmoRepEspacada()
    
    card_estudo = Cardmanual(dados['frente'], dados['verso'], algoritmo)
    card_estudo.intervalo = dados['intervalo'] # cria o objeto do card e pega o estado dele do banco
    
    data_proxima = card_estudo.revisao(req.nota) # Calculando a revisao
    
    # Salvar essa atualizacao no supa
    supabase.table("flashcards").update({"intervalo": card_estudo.intervalo,
        "proxima_revisao": data_proxima.isoformat(), "erros_consecutivos": novos_erros}).eq("id", req.card_id).execute()
    
    user_id_do_card = dados['user_id']
    hoje = date.today().isoformat()
    
    # Tenta achar o status do usuário
    stats = supabase.table("user_stats").select("*").eq("user_id", user_id_do_card).execute()
    
    if not stats.data:
        # Primeiro dia de estudo da vida dele!
        supabase.table("user_stats").insert({
            "user_id": user_id_do_card, 
            "streak": 1, 
            "ultima_revisao": hoje
        }).execute()
    else:
        # Já estudou antes, vamos ver se foi hoje
        ultima = stats.data[0].get("ultima_revisao")
        streak_atual = stats.data[0].get("streak", 0)
        
        if ultima != hoje:
            # É a primeira revisão do dia de hoje! Ganhou +1 no Streak.
            supabase.table("user_stats").update({
                "streak": streak_atual + 1, 
                "ultima_revisao": hoje
            }).eq("user_id", user_id_do_card).execute()
    
    return{
        "status": "sucesso", "erros": novos_erros, "novo_intervalo": card_estudo.intervalo, "proxima_data": data_proxima.strftime("%Y-%m-%d")
        
    }
    
class NovoDeck(BaseModel):
    nome: str
    user_id: str

@app.post("/criar-deck")
def criar_deck(deck: NovoDeck):
    try:
        resposta = supabase.table("decks").insert({"nome": deck.nome, "user_id": deck.user_id}).execute()
        
        id_gerado = resposta.data[0]['id']
        
        return {"status": "sucesso", "id": id_gerado, "nome": deck.nome}
    
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}

# 1 Listar todos os Decks
@app.get("/decks/{user_id}")
def listar_decks(user_id: str):
    res = supabase.table("decks").select("*").eq("user_id", user_id).execute()
    return {"status": "sucesso", "decks": res.data}

# 2 Listar cards de um deck específico
@app.get("/decks/{deck_id}/cards")
def listar_cards_do_deck(deck_id: str):
    res = supabase.table("flashcards").select("*").eq("deck_id", deck_id).execute()
    return {"status": "sucesso", "cards": res.data}

# 3 Criar Card Manual 
class CardSimples(BaseModel):
    deck_id: str
    user_id: str
    frente: str
    verso: str
    anexo: str = None

@app.post("/criar-card-manual")
def criar_card_manual(card: CardSimples):
    try:
        supabase.table("flashcards").insert({
            "deck_id": card.deck_id,
            "user_id": card.user_id,
            "frente": card.frente,
            "verso": card.verso,
            "tipo": "manual", 
            "metadata": card.anexo
        }).execute()
        return {"status": "sucesso"}
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}
    
from datetime import datetime # (Certifique-se de que isso está lá em cima nos imports)

@app.get("/estatisticas/{user_id}")
def obter_estatisticas(user_id: str):
    try:
        # 1. Puxa todos os cards com seus intervalos e erros
        res = supabase.table("flashcards").select("intervalo, erros_consecutivos, frente").eq("user_id", user_id).execute()
        all_cards = res.data if res.data else []
        
        # 2. Cálculo de Maturidade
        aprendendo = len([c for c in all_cards if c.get('intervalo', 0) < 3])
        familiar = len([c for c in all_cards if 3 <= c.get('intervalo', 0) <= 21])
        dominado = len([c for c in all_cards if c.get('intervalo', 0) > 21])
        
        # 3. Filtra os Sanguessugas direto no Python para garantir
        pontos_fracos = [{"frente": c["frente"], "erros_consecutivos": c["erros_consecutivos"]} 
                   for c in all_cards if c.get('erros_consecutivos', 0) >= 3]

        return {
            "status": "sucesso",
            "dados": {
                "total": len(all_cards),
                "maturidade": {"aprendendo": aprendendo, "familiar": familiar, "dominado": dominado},
                "pontos_fracos": pontos_fracos,
                "taxa_dominio": round((dominado / len(all_cards) * 100), 1) if all_cards else 0
            }
        }
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}

@app.get("/streak/{user_id}")
def obter_streak(user_id: str):
    try:
        res = supabase.table("user_stats").select("*").eq("user_id", user_id).execute()
        
        # Se o usuário é novo e ainda não tem registro, devolve 0
        if not res.data:
            return {"status": "sucesso", "streak": 0}
            
        dados = res.data[0]
        streak_atual = dados.get("streak", 0)
        ultima_revisao_str = dados.get("ultima_revisao")
        
        # Lógica de proteção: se ele ficou dias sem entrar, o streak "quebra" visualmente
        if ultima_revisao_str:
            ultima_revisao = date.fromisoformat(ultima_revisao_str)
            hoje = date.today()
            if (hoje - ultima_revisao).days > 1:
                streak_atual = 0 # Perdeu a ofensiva!
                
        return {"status": "sucesso", "streak": streak_atual}
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}
    
    # Modelo de dados para a requisição
class PedidoTutor(BaseModel):
    frente: str
    verso: str

@app.post("/tutor-ia")
def tutor_ia(pedido: PedidoTutor):
    try:
       
        prompt = f"""
        Aja como um professor particular empático. O aluno está estudando um flashcard:
        - Pergunta: {pedido.frente}
        - Resposta correta: {pedido.verso}
        
        Ele teve dificuldade em lembrar ou entender. Em no máximo 3 linhas (seja muito muito breve), 
        dê uma dica mnemônica, uma analogia simples ou um contexto rápido para ajudar a fixar a informação.
        Não repita a resposta inteira, dê a explicação, a dica, o que realmente vai ajudar e seja séria, voce é um tutor de estudos, não precisa de gracinhas. Só entregue explicacoes corretas.
        """
        '''
        resposta_ia = model.generate_content(prompt,generation_config=GenerationConfig(
                temperature=0.7))
        '''
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=150, # Restringe a resposta a cerca de 6 linhas (rápido e barato)
            temperature=0.7 # Um pouco mais de temperatura para o tutor ser didático
        )
        
        resposta_ia = response.choices[0].message.content
        return {"status": "sucesso", "explicacao": resposta_ia}
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}
