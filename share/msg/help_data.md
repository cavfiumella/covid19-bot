Le grandezze riportate per i *contagi* sono le seguenti:
\- *nuovi positivi*: nuovi casi positivi;
\- *totale positivi*: casi attualmente positivi;
\- *ricoverati con sintomi*: casi ricoverati in ospedale con sintomi;
\- *terapia intensiva*: casi ricoverati in terapia intensiva;
\- *isolamento domiciliare*: casi in isolamento domiciliare;
\- *dimessi guariti*: casi guariti;
\- *deceduti*: casi deceduti;
\- *tamponi*: tamponi eseguiti;
\- *tamponi test molecolare*: tamponi molecolari eseguiti;
\- *tamponi test antigenico rapido* tamponi antigenici rapidi eseguiti\.

Le grandezze riportate per le *vaccinazioni* sono le seguenti:
\- *prima dose*: numero di prime dosi somministrate;
\- *seconda dose*: numero di seconde dosi somministrate;
\- *pregressa infezione*: numero di casi con pregressa infezione (è da considerarsi come sostitutiva di una dose di vaccino);
\- *dose addizionale booster*: numero di terze dosi somministrate

Per ogni variabile vengono generati i seguenti valori calcolati nel periodo di riferimento (i\.e\. giorno, settimana o mese):
\- *totale*, valore complessivo,
\- *media*, valore medio giornaliero,
\- *dev std*, deviazione standard,
\- *var pct*, variazione percentuale della media giornaliera rispetto al periodo precedente; e\.g\. per un report mensile la variazione considera la media del mese precedente e quella del mese di riferimento\.

I valori precedenti vengono calcolati per tutti i periodi di riferimento ma mentre questi sono tutti validi per settimana e mese, non lo sono per il *giorno*\.
Per i report giornalieri dei *contagi* _totale_ e _media_ corrispondono entrambi al valore assoluto del giorno di riferimento e la _dev std_ è nulla\.
Nel caso delle *vaccinazioni* invece _totale_ e _media_ non corrispondono e la _dev std_ non è nulla; questo accade perché mentre per i contagi viene riportato un valore per giorno nel dataset originale, per i vaccini i dati sono suddivisi oltre che per giorno, per tipologia di vaccino e fascia anagrafica a cui è stato somministrato\.
Nei report sulle vaccinazioni allo stato attuale è più utile ignorare _media_ e _dev std_ visto che vanno a considerare due informazioni (i\.e\. tipologia e fascia anagrafica) che per il momento non sono direttamente accessibili dai dati presenti negli aggiornamenti\.

Se si desidera accedere a *più informazioni* sui contagi o sulle vaccinazioni usare il comando `/dashboard` e seguire il link che viene fornito per avere a disposizione grafici interattivi completi, dove anche la tipologia di dose e la fascia anagrafica vengono considerate nella presentazione dei dati\.
