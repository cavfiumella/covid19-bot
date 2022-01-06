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
Gli aggiornamenti riportano una serie di valori comuni a tutti i report e che dipendono solo dalle fonti scelte: contagi e vaccini.
Per ogni variabile vengono generati i seguenti valori calcolati nel periodo di riferimento (i.e. giorno, settimana o mese in base alla frequenza del report):
- **totale**, valore complessivo,
- **media**, valore medio giornaliero, che corrisponde al valore assoluto per la frequenza giornaliera,
- **dev std**, deviazione standard, mancante nei report giornalieri,
- **var pct**, variazione percentuale della media giornaliera rispetto al periodo precedente; e.g. per un report mensile la variazione considera la media del mese precedente e quella del mese di riferimento.

### Ulteriori riferimenti
Per **ulteriori informazioni** non esitare a scrivere in [Q&A](https://github.com/cavfiumella/covid19-bot/discussions/categories/q-a).

**Aggiornamenti** sulle nuove versioni e sulle nuove funzionalità vengono pubblicati nella sezione [annunci](https://github.com/cavfiumella/covid19-bot/discussions/categories/annunci).

I **bug** scoperti sono tracciati alla pagina [issues](https://github.com/cavfiumella/covid19-bot/issues).
