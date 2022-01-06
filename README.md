[![CodeQL](https://github.com/cavfiumella/covid19-bot/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/cavfiumella/covid19-bot/actions/workflows/codeql-analysis.yml)

# Covid-19 Bot
## Bot Telegram per la ricezione di aggiornamenti su contagi e vaccinazioni da Covid-19 in Italia

Il bot è stato rilasciato ed è contattabile a questo [link](https://t.me/cavfiumella_covid19_bot).

### Comandi
Il bot permette di ricevere aggiornamenti sui contagi e sulle vaccinazioni da Covid-19 in Italia.

I comandi disponibili sono i seguenti:
- `/start` stampa un messaggio di benvenuto all'avvio del bot,
- `/help` stampa un elenco dei comandi disponibile con una breve descrizione sul loro uso,
- `/attiva_report` avvia una conversazione con cui impostare la ricezione degli aggiornamenti,
- `/disattiva_report` disattiva gli aggiornamenti,
- `/stato_report` visualizza le impostazioni attuali,
- `/dashboard` visualizza una dashboard completa con grafici sui contagi e sulle vaccinazioni,
- `/bug` stampa un messaggio con i riferimenti per la segnalazione di un errore,
- `/feedback` stampa un messaggio con i riferimenti per lasciare un suggerimento,
- `/versione` visualizza versione del bot

### Report

#### Impostazioni
Eseguito il comando `/attiva_report` all'utente viene chiesto di impostare le seguenti impostazioni:
- **formato** del report,
- **periodi di riferimento** del report,
- **aree** du cui ricevere gli aggiornamenti dei **contagi**,
- **aree** du cui ricevere gli aggiornamenti delle **vaccinazioni**.

I _formati_ tra cui scegliere sono:
- **testuale**,
- **Excel**.

I _periodi di riferimento_ tra cui scegliere sono:
- **giorno**
- **settimana**
- **mese**.

Le _aree_ a disposizione per _contagi e vaccinazioni_ sono:
- **Italia**,
- le varie **regioni**,
- le **provincie autonome**.

#### Modalità di invio
Il bot prevede una modalità automatica di **non disturbare** che impedisce l'invio di messaggi agli utenti **tra le 21:00 e le 10:00**.

I report su contagi e vaccinazioni vengono inviati separatamente appena i dati ala sorgente vengono aggiornati.
I dati sui contagi vengono caricati tra le 17:00 e le 18:00 del giorno di riferimento mentre i dati sulle vaccinazioni intorno alle 05:00 del giorno successivo.
Solitamente quindi i report del giorno corrente sui contagi arrivano nel tardo pomeriggio, quelli sulle vaccinazioni il giorno seguente.

#### Valori del report
Gli aggiornamenti riportano una serie di valori comuni a tutti i report che dipendono solo dalle fonti: contagi e vaccini.

Le grandezze riportate per i **contagi** sono le seguenti:
- **nuovi positivi**: nuovi casi positivi;
- **totale positivi**: casi attualmente positivi;
- **ricoverati con sintomi**: casi ricoverati in ospedale con sintomi;
- **terapia intensiva**: casi ricoverati in terapia intensiva;
- **isolamento domiciliare**: casi in isolamento domiciliare;
- **dimessi guariti**: casi guariti;
- **deceduti**: casi deceduti;
- **tamponi**: tamponi eseguiti;
- **tamponi test molecolare**: tamponi molecolari eseguiti;
- **tamponi test antigenico rapido** tamponi antigenici rapidi eseguiti.

Le grandezze riportate per le **vaccinazioni** sono le seguenti:
- **prima dose**: numero di prime dosi somministrate;
- **seconda dose**: numero di seconde dosi somministrate;
- **pregressa infezione**: numero di casi con pregressa infezione (è da considerarsi come sostitutiva di una dose di vaccino);
- **dose addizionale booster**: numero di terze dosi somministrate

Per ogni variabile vengono generati i seguenti valori calcolati nel periodo di riferimento (i.e. giorno, settimana o mese):
- **totale**, valore complessivo,
- **media**, valore medio giornaliero,
- **dev std**, deviazione standard,
- **var pct**, variazione percentuale della media giornaliera rispetto al periodo precedente; e.g. per un report mensile la variazione considera la media del mese precedente e quella del mese di riferimento.

I valori precedenti vengono calcolati per tutti i periodi di riferimento ma mentre questi sono tutti validi per settimana e mese, non lo sono per il **giorno**.
Per i report giornalieri dei **contagi** _totale_ e _media_ corrispondono entrambi al valore assoluto del giorno di riferimento e la _dev std_ è nulla.
Nel caso delle **vaccinazioni** invece _totale_ e _media_ non corrispondono e la _dev std_ non è nulla; questo accade perché mentre per i contagi viene riportato un valore per giorno nel dataset originale, per i vaccini i dati sono suddivisi oltre che per giorno, per tipologia di vaccino e fascia anagrafica a cui è stato somministrato.
Nei report sulle vaccinazioni allo stato attuale è più utile ignorare _media_ e _dev std_ visto che vanno a considerare due informazioni (i.e. tipologia e fascia anagrafica) che per il momento non sono direttamente accessibili dai dati presenti negli aggiornamenti.

Se si desidera accedere a **più informazioni** sui contagi o sulle vaccinazioni usare il comando `/dashboard` e seguire il link che viene fornito per avere a disposizione grafici interattivi completi, dove anche la tipologia di dose e la fascia anagrafica vengono considerate nella presentazione dei dati.

### Ulteriori riferimenti
Per **ulteriori informazioni** non esitare a scrivere in [Q&A](https://github.com/cavfiumella/covid19-bot/discussions/categories/q-a).

**Aggiornamenti** sulle nuove versioni e sulle nuove funzionalità vengono pubblicati nella sezione [annunci](https://github.com/cavfiumella/covid19-bot/discussions/categories/annunci).

I **bug** scoperti sono tracciati alla pagina [issues](https://github.com/cavfiumella/covid19-bot/issues).
