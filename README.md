[![CodeQL](https://github.com/cavfiumella/covid19-bot/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/cavfiumella/covid19-bot/actions/workflows/codeql-analysis.yml)

# Covid-19 Bot
## Bot Telegram per la ricezione di aggiornamenti su contagi e vaccinazioni da Covid-19 in Italia

Il bot è stato rilasciato ed è contattabile a questo [link](https://t.me/cavfiumella_covid19_bot).

E' possibile ricevere aggiornamenti sui contagi e sulle vaccinazioni da Covid-19.

### Report
Gli aggiornamenti vengono inviati **tra le 10:00 e le 21:00** in base alla disponibilità dei dati.
I report vengono generati e inviati in un **unico messaggio** in modo da ridurre il numero di notifiche giornaliere a 1.
Se anche solo alcuni dei dati sono mancanti, il bot non invia il report fino a che il dataset non è completo.

I report possono essere generati **giornalmente, settimanalmente (questa è la _frequenza consigliata_) e mensilmente**.
Le variabili utilizzate nei report sono le stesse per tutti e dipendono dalle fonti scelte.
I **dati disponibili** sono quelli nazionali e regionali per contagi e vaccinazioni.


Per ogni variabile presa in considerazione nei dati vengono generati i **seguenti valori**:
- **_totale_**: valore complessivo della variabile nel periodo di riferimento (i.e. giorno, settimana, mese rispettivamente per frequenza giornaliera, settimanale e mensile);
- **_media_**: valore medio giornaliero della variabile calcolato nel periodo di riferimento;
- **_dev std_**: deviazione standard della variabile calcolata nel periodo di riferimento;
- **_var pct_**: variazione percentuale del valore medio giornaliero rispetto al periodo precedente (e.g. in un report mensile la variazione percentuale viene calcolata considerando la media del mese precedente a quello del report generato).

### Riferimenti
Per **ulteriori informazioni** non esitare a scrivere in [Q&A](https://github.com/cavfiumella/covid19-bot/discussions/categories/q-a).

**Aggiornamenti** sui rilasci e le funzionalità vengono pubblicati nella sezione [Annunci](https://github.com/cavfiumella/covid19-bot/discussions/categories/annunci).

Gli **errori** sono tracciati alla pagina [issues](https://github.com/cavfiumella/covid19-bot/issues).
