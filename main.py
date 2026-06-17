import { useState, useEffect } from 'react'
import { supabase } from './supabaseClient'
import './App.css' // Importação do arquivo de estilos

function App() {
  // --- ESTADOS DE AUTENTICAÇÃO ---
  const [session, setSession] = useState(null)
  const [emailAuth, setEmailAuth] = useState('')
  const [senhaAuth, setSenhaAuth] = useState('')
  const [streak, setStreak] = useState(0)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
    })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })
    return () => subscription.unsubscribe()
  }, [])

  const handleCadastro = async () => {
    const { error } = await supabase.auth.signUp({ email: emailAuth, password: senhaAuth })
    if (error) alert(error.message)
    else alert("Cadastro realizado! Você já pode entrar.")
  }

  const handleLogin = async () => {
    const { error } = await supabase.auth.signInWithPassword({ email: emailAuth, password: senhaAuth })
    if (error) alert(error.message)
  }

  const handleSair = async () => {
    await supabase.auth.signOut()
  }

  // --- ESTADOS DO APP ---
  const [aba, setAba] = useState('dashboard') 
  const [texto, setTexto] = useState('')
  const [cardsIA, setCardsIA] = useState([])
  const [cardsRevisao, setCardsRevisao] = useState([])
  const [cardAtualIdx, setCardAtualIdx] = useState(0)
  const [mostrarVerso, setMostrarVerso] = useState(false)
  const [nomeDeck, setNomeDeck] = useState('')
  const [idDeckAtivo, setIdDeckAtivo] = useState(null) 
  const [listaDecks, setListaDecks] = useState([])
  const [cardsDoDeckSelecionado, setCardsDoDeckSelecionado] = useState([])
  const [nomeDeckSelecionado, setNomeDeckSelecionado] = useState('')
  const [estatisticas, setEstatisticas] = useState({ total: 0, maturidade: { aprendendo: 0, familiar: 0, dominado: 0 }, leeches: [], taxa_dominio: 0 })
  const [explicacaoTutor, setExplicacaoTutor] = useState(null)
  const [carregandoTutor, setCarregandoTutor] = useState(false)

  useEffect(() => {
    if (session) {
      // Busca o Foguinho 🔥
      fetch(`https://easycards-api.onrender.com/streak/${session.user.id}`)
        .then(res => res.json())
        .then(d => { if(d.status === 'sucesso') setStreak(d.streak) })

      if (aba === 'meus_decks') fetch(`https://easycards-api.onrender.com/decks/${session.user.id}`).then(res => res.json()).then(d => setListaDecks(d.decks || []))
      if (aba === 'dashboard') fetch(`https://easycards-api.onrender.com/estatisticas/${session.user.id}`).then(res => res.json()).then(d => { if(d.status === 'sucesso') setEstatisticas(d.dados) })
      if (aba === 'revisar') carregarCardsRevisao()
    }
  }, [aba, session])

  const carregarCardsDoDeck = async (deckId, deckNome) => {
    const res = await fetch(`https://easycards-api.onrender.com/decks/${deckId}/cards`); 
    const dados = await res.json();
    setCardsDoDeckSelecionado(dados.cards); setNomeDeckSelecionado(deckNome);
  }

const handleCriarDeck = async () => {
    if (!nomeDeck) return alert("Voce precisa nomear seu deck");
    const res = await fetch('https://easycards-api.onrender.com/criar-deck', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: nomeDeck, user_id: session.user.id }) });
    const dados = await res.json();
    
    if (dados.status === "sucesso") { 
      setIdDeckAtivo(dados.id); 
      alert(`Deck criado!`); 
      carregarDecks(); 
    } else {
      alert(dados.detalhes);
    }
  };

  const salvarCardsNoBanco = async () => {
    if (!idDeckAtivo) return alert("Crie ou selecione um Deck primeiro!");
    const cardsComDono = cardsIA.map(card => ({ ...card, user_id: session.user.id }));
    await fetch('https://easycards-api.onrender.com/salvar-cards-ia', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deck_id: idDeckAtivo, cards: cardsComDono }) });
    alert("✅ Cards salvos!"); setCardsIA([]); 
  }

  const carregarCardsRevisao = async () => {
    const res = await fetch(`https://easycards-api.onrender.com/cards-para-revisar/${session.user.id}`);
    const dados = await res.json();
    setCardsRevisao(dados.cards || []);
    setCardAtualIdx(0);
    setMostrarVerso(false);
  }

  const enviarNota = async (nota) => {
    setExplicacaoTutor(null);
    const card = cardsRevisao[cardAtualIdx];
    await fetch('https://easycards-api.onrender.com/processo-revisao', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ card_id: card.id, nota: nota, user_id: session.user.id}) });
    
    if (cardAtualIdx < cardsRevisao.length - 1) { 
      setCardAtualIdx(cardAtualIdx + 1); 
      setMostrarVerso(false); 
    } else { 
      alert("🎉 Revisão concluída!"); 
      // Lógica do Foguinho: Se estava em 0, vai para 1 visualmente.
      setStreak(prev => (prev === 0 ? 1 : prev)); 
      setAba('dashboard'); 
    }
  }

  const pedirAjudaTutor = async () => {
    setCarregandoTutor(true);
    const card = cardsRevisao[cardAtualIdx];
    try {
      const res = await fetch('https://easycards-api.onrender.com/tutor-ia', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ frente: card.frente, verso: card.verso }) });
      const d = await res.json();
      
      // Agora o React te avisa se a cota estourar!
      if (d.status === "sucesso") {
        setExplicacaoTutor(d.explicacao);
      } else {
        alert("Erro no Tutor IA: " + d.detalhes); 
      }
      
    } catch (error) { alert("Erro ao chamar o tutor."); }
    setCarregandoTutor(false);
  }

  const desfazerUltimaNota = async () => {
    try {
      const res = await fetch('https://easycards-api.onrender.com/desfazer-revisao', { method: 'POST' });
      const d = await res.json();
      
      if (d.status === 'sucesso') {
        alert("Ação desfeita! O banco de dados voltou ao estado anterior.");
        setCardAtualIdx(cardAtualIdx - 1); 
        setMostrarVerso(false);
      } else {
        alert(d.mensagem);
      }
    } catch (error) { 
      alert("Erro ao tentar desfazer a revisão."); 
    }
  }

  if (!session) {
    return (
      <div className="auth-container">
        <div className="auth-box">
          <h1 className="auth-title">🧠 Easy Cards</h1>
          <p className="auth-subtitle">O seu mentor inteligente.</p>
          <input className="auth-input" type="email" placeholder="Seu melhor e-mail" value={emailAuth} onChange={(e) => setEmailAuth(e.target.value)} />
          <input className="auth-input" type="password" placeholder="Senha secreta" value={senhaAuth} onChange={(e) => setSenhaAuth(e.target.value)} />
          <button className="auth-btn-login" onClick={handleLogin}>Entrar no Sistema</button>
          <button className="auth-btn-register" onClick={handleCadastro}>Criar minha conta</button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-wrapper">
      <div className="user-bar">
        <div className="user-info">
          <span className="user-email">👤 {session.user.email}</span>
          <span className="streak-badge">🔥 {streak} Dias Seguidos</span>
        </div>
        <button className="btn-logout" onClick={handleSair}>Sair</button>
      </div>

      <h1 className="app-title">🧠 Easy Cards</h1>
      
      <nav className="navbar">
        <button onClick={() => setAba('dashboard')} className="nav-btn" style={{ backgroundColor: aba === 'dashboard' ? '#f39c12' : '#bdc3c7' }}>📊 Dashboard</button>
        <button onClick={() => setAba('gerar')} className="nav-btn" style={{ backgroundColor: aba === 'gerar' ? '#2ecc71' : '#bdc3c7' }}>✨ Criar Cards</button>
        <button onClick={() => setAba('revisar')} className="nav-btn" style={{ backgroundColor: aba === 'revisar' ? '#3498db' : '#bdc3c7' }}>📚 Estudar Hoje</button>
        <button onClick={() => setAba('meus_decks')} className="nav-btn" style={{ backgroundColor: aba === 'meus_decks' ? '#9b59b6' : '#bdc3c7' }}>📂 Meus Decks</button>
      </nav>

      {aba === 'dashboard' && (
        <div className="dashboard-content">
          <div className="stats-row">
            <div className="stat-card bg-dark">
              <p className="stat-label">Total de Cards</p>
              <h2 className="stat-value">{estatisticas.total}</h2>
            </div>
            <div className="stat-card bg-green">
              <p className="stat-label">Taxa de Domínio</p>
              <h2 className="stat-value">{estatisticas.taxa_dominio}%</h2>
            </div>
          </div>
          <h3 className="section-title">Maturidade do Conhecimento</h3>
          <div className="maturity-row">
            <div className="maturity-card border-red">
              <h4 className="txt-red">🌱 Aprendendo</h4><p className="maturity-num">{estatisticas.maturidade.aprendendo}</p>
            </div>
            <div className="maturity-card border-yellow">
              <h4 className="txt-yellow">🌿 Familiar</h4><p className="maturity-num">{estatisticas.maturidade.familiar}</p>
            </div>
            <div className="maturity-card border-green">
              <h4 className="txt-green">🌳 Dominado</h4><p className="maturity-num">{estatisticas.maturidade.dominado}</p>
            </div>
          </div>
          {estatisticas.leeches && estatisticas.leeches.length > 0 && (
            <div className="leeches-alert">
              <h3 className="leeches-title">⚠️ Alerta de Pontos Fracos (Leeches)</h3>
              <ul className="leeches-list">
                {estatisticas.leeches.map((l, i) => <li key={i}><strong>{l.erros_consecutivos} erros:</strong> {l.frente}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {aba === 'gerar' && (
        <div className="gerar-content"> 
          <div className="deck-selector">
            <h3>1º Passo: Definir o Deck Alvo</h3>
            <input className="input-deck" type="text" placeholder="Ex: Anatomia Humana" value={nomeDeck} onChange={(e) => setNomeDeck(e.target.value)} />
            <button className="btn-create-deck" onClick={handleCriarDeck}>Criar Deck</button>
            {idDeckAtivo && <p className="active-deck-txt">✅ Destino: {nomeDeck} (Ativo)</p>}
          </div>
          <div className="creation-methods">
            <div className="method-card manual">
              <h4>✍️ Criar Manualmente</h4>
              <input className="full-input" placeholder="Digite a Pergunta..." id="manualFrente" />
              <textarea className="full-input" placeholder="Digite a Resposta..." rows="3" id="manualVerso" />

              <input className="full-input" placeholder="Link, Contexto ou Referência (Opcional)..." id="manualAnexo" />
              
              <button className="btn-save-manual" onClick={async () => {
                if (!idDeckAtivo) return alert("Defina o Deck primeiro!");
          
                const f = document.getElementById('manualFrente').value;
                const v = document.getElementById('manualVerso').value;
                const a = document.getElementById('manualAnexo').value;
                await fetch('https://easycards-api.onrender.com/criar-card-manual', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ deck_id: idDeckAtivo, user_id: session.user.id, frente: f, verso: v, anexo: a }) });
                alert("Salvo!"); document.getElementById('manualFrente').value = ''; document.getElementById('manualVerso').value = ''; document.getElementById('manualAnexo').value = '';
              }}>Salvar Card Manual</button>
            </div>
            <div className="method-card ia">
              <h4>✨ Extração por IA</h4>
              <textarea className="full-input" value={texto} onChange={(e) => setTexto(e.target.value)} rows="4" placeholder="Cole o texto aqui..." />
              <button className="btn-extract-ia" onClick={async () => {
                 const res = await fetch('https://easycards-api.onrender.com/gerar-cards-ia', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texto_contexto: texto }) })
                 const d = await res.json(); setCardsIA(d.cards);
              }}>Extrair Cards</button>
            </div>
          </div>
          {cardsIA.length > 0 && (
            <div className="ia-review">
              <h3>Revise e Edite:</h3>
              {cardsIA.map((c, i) => (
                <div key={i} className="edit-card">
                  <textarea className="edit-area" value={c.frente} onChange={(e) => { const novos = [...cardsIA]; novos[i].frente = e.target.value; setCardsIA(novos); }} rows="2" />
                  <textarea className="edit-area" value={c.verso} onChange={(e) => { const novos = [...cardsIA]; novos[i].verso = e.target.value; setCardsIA(novos); }} rows="2" />
                </div>
              ))}
              <button className="btn-save-all" onClick={salvarCardsNoBanco}>💾 Salvar Tudo</button>
            </div>
          )}
        </div>
      )}

      {aba === 'revisar' && (
        <div className="revisar-content">
          <h2>Sessão de Estudos</h2>
          {cardAtualIdx > 0 && (
            <button onClick={desfazerUltimaNota} className="btn-undo">
              ↩️ Ops, cliquei errado! Desfazer nota anterior
            </button>
          )}
          {cardsRevisao.length > 0 ? (
            <div className="study-card">
              <h3 className="card-frente">{cardsRevisao[cardAtualIdx].frente}</h3>
              {mostrarVerso ? (
                <div>
                  <hr className="card-divider"/>
                  <p className="card-verso">{cardsRevisao[cardAtualIdx].verso}</p>
                   {cardsRevisao[cardAtualIdx].metadata && ( <div className="card-metadata-box">
                     <p className="metadata-label">🔗 Referência de Estudo:</p>
                     <p className="metadata-content">{cardsRevisao[cardAtualIdx].metadata}</p>
                   </div>
                      )}
                  <div className="btn-group">
                    <button onClick={() => enviarNota(0)} className="btn-note btn-red">0 - Errei</button>
                    <button onClick={() => enviarNota(3)} className="btn-note btn-blue">3 - Difícil</button>
                    <button onClick={() => enviarNota(5)} className="btn-note btn-green">5 - Fácil</button>
                  </div>
                  <div className="tutor-section">
                    {!explicacaoTutor && !carregandoTutor && (
                      <button onClick={pedirAjudaTutor} className="btn-tutor">🤖 Não entendi. Pedir dica ao Tutor IA</button>
                    )}
                    {carregandoTutor && <p className="tutor-loading">O tutor está formulando uma dica...</p>}
                    {explicacaoTutor && (
                      <div className="tutor-result">
                        <h4 className="tutor-header">💡 Dica do Mentor:</h4>
                        <p className="tutor-text">{explicacaoTutor}</p>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <button onClick={() => setMostrarVerso(true)} className="btn-show">👀 Mostrar Resposta</button>
              )}
            </div>
          ) : (<p>✅ Você já revisou todos os cards de hoje.</p>)}
        </div>
      )}

      {aba === 'meus_decks' && (
        <div className="decks-content">
          <h2>📂 Gerenciador de Decks</h2>
          <div className="decks-layout">
            <div className="decks-list">
              {listaDecks.map((deck) => (
                <button key={deck.id} onClick={() => carregarCardsDoDeck(deck.id, deck.nome)} className="deck-item">📘 {deck.nome}</button>
              ))}
            </div>
            <div className="deck-viewer">
              {nomeDeckSelecionado ? (
                <>
                  <h4>Cards em: {nomeDeckSelecionado}</h4>
                  <div className="cards-scroll">
                    {cardsDoDeckSelecionado.map((card, idx) => (
                      <div key={idx} className="card-list-item">
                        <p><strong>P:</strong> {card.frente}</p><p><strong>R:</strong> {card.verso}</p>
                      </div>
                    ))}
                  </div>
                </>
              ) : (<p></p>)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
