[![CodeQL](https://github.com/cavfiumella/covid19-bot/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/cavfiumella/covid19-bot/actions/workflows/codeql-analysis.yml)

# Covid-19 Bot
## Bot Telegram per la ricezione di aggiornamenti su contagi e vaccinazioni da Covid-19 in Italia

Il bot è stato rilasciato ed è contattabile a questo [link](https://t.me/cavfiumella_covid19_bot).

### Comandi
Il bot permette di ricevere aggiornamenti sui contagi e sulle vaccinazioni da Covid-19 in Italia.

I comandi disponibili sono i seguenti:
- `/start` stampa un messaggio di benvenuto all'avvio del bot,
- `/help` stampa un elenco dei comandi disponibile con una breve descrizione sul loro uso,
- `/imposta_report` avvia una conversazione con cui impostare la ricezione degli aggiornamenti,
- `/disattiva_report` disattiva gli aggiornamenti,
- `/stato_report` visualizza le impostazioni attuali,
- `/bug` stampa un messaggio con i riferimenti per la segnalazione di un errore,
- `/feedback` stampa un messaggio con i riferimenti per lasciare un suggerimento.

### Report

#### Impostazioni
Eseguito il comando `/imposta_report` all'utente viene chiesto di impostare le seguenti impostazioni:
- **frequenza degli aggiornamenti**,
- ricezione degli aggiornamenti sui **contagi in Italia**,
- ricezione degli aggiornamenti sui **contagi in una regione**,
- ricezione degli aggiornamenti sulle **vaccinazioni in Italia**,
- ricezione degli aggiornamenti sulle **vaccinazioni in una regione**.

Le frequenze di aggiornamento tra cui scegliere sono:
- **giornaliera**
- **settimanale**
- **mensile**.

#### Modalità di invio
I report vengono inviati in un **unico messaggio** per ridurre il numero giornaliero di notifiche.
Se una parte dei dati richiesti sono mancanti il bot non invia il report fino a che i dataset non sono completi.
I dati sui contagi vengono caricati tra le 17:00 e le 18:00 del giorno di riferimento mentre i dati sulle vaccinazioni intorno alle 05:00.
Il bot prevede una modalità automatica di **non disturbare** che impedisce l'invio di messaggi agli utenti **tra le 21:00 e le 10:00**.
Se quindi l'utente sceglie di ricevere aggiornamenti su contagi e vaccinazioni e la frequenza è giornaliera, i report verranno inviati il giorno successivo a quello di riferimento; diversamente, se solo i contagi sono attivi il report viene consegnato la sera stessa.

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
