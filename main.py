import os
from dotenv import load_dotenv
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import json
from supabase import create_client, Client

load_dotenv()

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

# ====================================================
# INÍCIO DA IMPLEMENTAÇÃO DO PADRÃO CRIACIONAL: ABSTRACT FACTORY
# ====================================================   
class FabricaDeCardsAbstrata(ABC):
    @abstractmethod
    def criar_combo_revisao(self, dados) -> BaseCard:
        pass

class FabricaCardManual(FabricaDeCardsAbstrata):
    def criar_combo_revisao(self, dados) -> Cardmanual:
        algoritmo = AlgoritmoRepEspacada()
        card = Cardmanual(dados['frente'], dados['verso'], algoritmo)
        card.intervalo = dados.get('intervalo', 0)
        return card

class FabricaCardIA(FabricaDeCardsAbstrata):
    def criar_combo_revisao(self, dados) -> CardIA:
        algoritmo = AlgoritmoIA()
        contexto = dados.get('metadata', '') 
        card = CardIA(dados['frente'], dados['verso'], algoritmo, contexto)
        card.intervalo = dados.get('intervalo', 0)
        return card

# ====================================================
# INÍCIO DO PADRÃO ESTRUTURAL: PROXY
# ====================================================
class TutorProxy:
    @staticmethod
    def obter_dica(frente: str, verso: str) -> str:
        pergunta_chave = f"{frente} - {verso}"

        # 1. Verifica no "cache" (Supabase)
        try:
            res = supabase.table("dicas_cache").select("dica").eq("pergunta", pergunta_chave).execute()
            if res.data:
                return res.data[0]["dica"] # Cache Hit: Devolve sem chamar a IA!
        except Exception:
            pass # Se der erro no banco ou não existir a tabela ainda, ignora e segue para a IA

        # 2. Se não achou (Cache Miss), chama a IA
        prompt = f"""
        Aja como um professor particular empático. O aluno está estudando um flashcard:
        - Pergunta: {frente}
        - Resposta correta: {verso}
        Ele teve dificuldade em lembrar. Em no máximo 3 linhas, dê uma dica mnemônica ou contexto rápido. 
        Não repita a resposta inteira, dê a explicação e seja sério.
        """
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7
        )
        resposta_ia = response.choices[0].message.content

        # 3. Salva a nova dica no cache para o futuro
        try:
            supabase.table("dicas_cache").insert({
                "pergunta": pergunta_chave,
                "dica": resposta_ia
            }).execute()
        except Exception:
            pass

        return resposta_ia

# ====================================================
# INÍCIO DO PADRÃO COMPORTAMENTAL: COMMAND
# ====================================================
class ComandoRevisarCard:
    def __init__(self, card_id: str, nota: int, dados_banco: dict):
        self.card_id = card_id
        self.nota = nota
        
        # Guarda o estado ANTERIOR para permitir o "Desfazer"
        self.intervalo_antigo = dados_banco.get('intervalo', 0)
        self.proxima_revisao_antiga = dados_banco.get('proxima_revisao')
        self.erros_antigos = dados_banco.get('erros_consecutivos', 0)
    
    def executar(self, card_estudo):
        if self.nota < 3:
            novos_erros = self.erros_antigos + 1
        else:
            novos_erros = 0
            
        data_proxima = card_estudo.revisao(self.nota)
        novo_intervalo = card_estudo.intervalo
        
        supabase.table("flashcards").update({
            "intervalo": novo_intervalo,
            "proxima_revisao": data_proxima.isoformat(),
            "erros_consecutivos": novos_erros
        }).eq("id", self.card_id).execute()
        
        return novo_intervalo, data_proxima, novos_erros

    def desfazer(self):
        # Proteção extra: impede que o código quebre ao tentar salvar dados vazios
        dados_restaurar = {
            "intervalo": self.intervalo_antigo if self.intervalo_antigo is not None else 0,
            "erros_consecutivos": self.erros_antigos if self.erros_antigos is not None else 0
        }
        
        # Só atualiza a data se ela realmente existia antes
        if self.proxima_revisao_antiga is not None:
            dados_restaurar["proxima_revisao"] = self.proxima_revisao_antiga

        # Restaura o banco para o estado exato antes do clique
        supabase.table("flashcards").update(dados_restaurar).eq("id", self.card_id).execute()

# Armazena o último comando temporariamente na memória RAM
ultimo_comando_executado = None

# ====================================================
# CONFIGURAÇÕES DO FASTAPI E ROTAS
# ====================================================
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
    return {"mensagem": "API rodando em arquivo unico com Padrões GoF!"}
    
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
    
    deck_id = resposta_deck.data[0]['id'] 
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
    prompt = f"""
    Atue como assistente de estudos, com foco na criação de flashcards. Leia o texto abaixo e extraia os três conceitos mais importantes e formate-os como perguntas e respostas sucintas.
    Retorne somente um JSON válido no seguinte formato de lista, sem explicações extras e sem blocos de código markdown (```json):
    [
        {{"frente": "pergunta", "verso": "resposta"}}
    ]
    Texto: {req.texto_contexto}
    """
    try: 
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Você é um assistente que gera apenas JSON puro."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3 
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
    try: 
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
    
@app.get("/cards-para-revisar/{user_id}")
def buscar_cards_revisao(user_id: str):
    try:
        agora = datetime.now().isoformat()
        resposta = supabase.table("flashcards")\
        .select("*")\
        .eq("user_id", user_id)\
        .lte("proxima_revisao", agora)\
        .execute()
        return {"status": "sucesso", "cards": resposta.data}
    except Exception as e:
        return { "status": "erro"}

class ReqProcessoRevisao(BaseModel):
    card_id: str
    nota: int
    
@app.post("/processo-revisao")
def processo_revisao(req: ReqProcessoRevisao):
    global ultimo_comando_executado
    
    res = supabase.table("flashcards").select("*").eq("id", req.card_id).single().execute()
    dados = res.data 

    # 1. Uso do Abstract Factory
    if dados.get('tipo') == 'IA':
        fabrica = FabricaCardIA()
    else:
        fabrica = FabricaCardManual()
   
    card_estudo = fabrica.criar_combo_revisao(dados)
    
    # 2. Uso do Command
    comando = ComandoRevisarCard(req.card_id, req.nota, dados)
    novo_intervalo, data_proxima, novos_erros = comando.executar(card_estudo)
    
    # Guarda na memória o comando caso o usuário queira desfazer
    ultimo_comando_executado = comando 
    
    user_id_do_card = dados['user_id']
    hoje = date.today().isoformat()
    
    # Atualização do Streak
    stats = supabase.table("user_stats").select("*").eq("user_id", user_id_do_card).execute()
    
    if not stats.data:
        supabase.table("user_stats").insert({
            "user_id": user_id_do_card, 
            "streak": 1, 
            "ultima_revisao": hoje
        }).execute()
    else:
        ultima = stats.data[0].get("ultima_revisao")
        streak_atual = stats.data[0].get("streak", 0)
        
        if ultima != hoje:
            supabase.table("user_stats").update({
                "streak": streak_atual + 1, 
                "ultima_revisao": hoje
            }).eq("user_id", user_id_do_card).execute()
    
    return{
        "status": "sucesso", "erros": novos_erros, "novo_intervalo": novo_intervalo, "proxima_data": data_proxima.strftime("%Y-%m-%d")
    }

# Rota nova para ativar o Padrão Command (Desfazer)
@app.post("/desfazer-revisao")
def desfazer_revisao():
    global ultimo_comando_executado
    try:
        if ultimo_comando_executado is not None:
            ultimo_comando_executado.desfazer()
            ultimo_comando_executado = None 
            return {"status": "sucesso", "mensagem": "Ação desfeita com sucesso. O card voltou ao estado original!"}
        else:
            return {"status": "erro", "mensagem": "Não há ações recentes para desfazer."}
    except Exception as e:
        # Agora, se houver falha, ele devolve a "mensagem" exata do erro e não "undefined"
        return {"status": "erro", "mensagem": f"Erro interno ao tentar desfazer: {str(e)}"}
    
class NovoDeck(BaseModel):
    nome: str
    user_id: str

@app.post("/criar-deck")
def criar_deck(deck: NovoDeck):
    try:
        # =========================================================
        # TRATAMENTO DE EXCEÇÃO 
        # =========================================================
        # 1. Busca no banco se este usuário já tem um deck com esse exato nome
        busca = supabase.table("decks").select("*").eq("user_id", deck.user_id).eq("nome", deck.nome).execute()
        
        # 2. Se a busca retornar algum resultado, a duplicidade foi detectada!
        if len(busca.data) > 0:
            # Levantamos a exceção ANTES do código tentar inserir no banco e quebrar
            raise ValueError(f"O deck '{deck.nome}' já existe na sua conta!")
        # =========================================================

        # Se passou pela verificação, insere normalmente
        resposta = supabase.table("decks").insert({"nome": deck.nome, "user_id": deck.user_id}).execute()
        id_gerado = resposta.data[0]['id']
        return {"status": "sucesso", "id": id_gerado, "nome": deck.nome}
    
    except ValueError as erro_duplicidade:
        # Tratamento ESPECÍFICO para o erro que nós mesmos levantamos
        return {"status": "erro", "detalhes": str(erro_duplicidade)}
        
    except Exception as e:
        # Tratamento GENÉRICO caso o banco de dados caia ou fique sem internet
        return {"status": "erro", "detalhes": "Erro interno no servidor. Tente novamente."}

@app.get("/decks/{user_id}")
def listar_decks(user_id: str):
    res = supabase.table("decks").select("*").eq("user_id", user_id).execute()
    return {"status": "sucesso", "decks": res.data}

@app.get("/decks/{deck_id}/cards")
def listar_cards_do_deck(deck_id: str):
    res = supabase.table("flashcards").select("*").eq("deck_id", deck_id).execute()
    return {"status": "sucesso", "cards": res.data}

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

@app.get("/estatisticas/{user_id}")
def obter_estatisticas(user_id: str):
    try:
        res = supabase.table("flashcards").select("intervalo, erros_consecutivos, frente").eq("user_id", user_id).execute()
        all_cards = res.data if res.data else []
        
        aprendendo = len([c for c in all_cards if c.get('intervalo', 0) < 3])
        familiar = len([c for c in all_cards if 3 <= c.get('intervalo', 0) <= 21])
        dominado = len([c for c in all_cards if c.get('intervalo', 0) > 21])
        
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
        
        if not res.data:
            return {"status": "sucesso", "streak": 0}
            
        dados = res.data[0]
        streak_atual = dados.get("streak", 0)
        ultima_revisao_str = dados.get("ultima_revisao")
        
        if ultima_revisao_str:
            ultima_revisao = date.fromisoformat(ultima_revisao_str)
            hoje = date.today()
            if (hoje - ultima_revisao).days > 1:
                streak_atual = 0 
                
        return {"status": "sucesso", "streak": streak_atual}
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}
    
class PedidoTutor(BaseModel):
    frente: str
    verso: str

@app.post("/tutor-ia")
def tutor_ia(pedido: PedidoTutor):
    try:
        # A chamada limpa usando o Padrão Proxy
        resposta_ia = TutorProxy.obter_dica(pedido.frente, pedido.verso)
        return {"status": "sucesso", "explicacao": resposta_ia}
    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}

@app.get("/enviar-lembretes")
def enviar_lembretes_estudo():
    try:
        agora = datetime.now().isoformat()
        res = supabase.table("flashcards")\
            .select("user_id")\
            .lte("proxima_revisao", agora)\
            .execute()

        cards_vencidos = res.data

        if not cards_vencidos:
            return {
                "status": "sucesso", 
                "mensagem": "Todos estão em dia! Nenhum lembrete necessário."
            }

        usuarios_para_notificar = set()
        for card in cards_vencidos:
            usuarios_para_notificar.add(card['user_id'])

        relatorio_envios = []
        for user in usuarios_para_notificar:
            mensagem = f"🔔 PUSH ENVIADO: Usuário {user}, você tem revisões pendentes no EasyCards!"
            print(mensagem) 
            relatorio_envios.append(mensagem)

        return {
            "status": "sucesso",
            "total_notificados": len(usuarios_para_notificar),
            "detalhes": relatorio_envios
        }

    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}
