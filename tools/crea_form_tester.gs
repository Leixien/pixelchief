/**
 * Crea il Google Form dei tester di PixelChief nel tuo account Google.
 *
 * 1. Apri https://script.google.com e premi "Nuovo progetto".
 * 2. Cancella il codice che c'è, incolla tutto questo file e salva.
 * 3. Scegli la funzione creaFormTester e premi Esegui; concedi i permessi richiesti.
 * 4. In "Log di esecuzione" trovi il link del form da mandare a chi gestisce il sito.
 * 5. Per ricevere una mail a ogni risposta: apri il form (link "Modifica"),
 *    scheda Risposte → ⋮ → "Ricevi notifiche via email per le nuove risposte".
 *
 * Il form ha tre pagine: prima chi sei e dove gira il gioco, poi solo le domande
 * per Google Play Games o solo quelle per BlueStacks, infine com'è andata.
 */
function creaFormTester() {
  const form = FormApp.create('PixelChief: prova dei tester');
  form.setDescription(
    'Grazie per aver provato PixelChief. Servono 3 minuti. ' +
    'Se una domanda non ti riguarda, lasciala vuota.');
  form.setProgressBar(true);
  form.setAllowResponseEdits(false);

  form.addTextItem().setTitle('Nome o nickname').setRequired(true);
  form.addTextItem()
    .setTitle('Versione di PixelChief')
    .setHelpText('La trovi nel nome della release che hai scaricato, per esempio 1.0.10.');
  const dove = form.addMultipleChoiceItem().setTitle('Dove gira il gioco?').setRequired(true);

  const gpg = form.addPageBreakItem()
    .setTitle('Google Play Games')
    .setHelpText('Domande sulla finestra del gioco in Google Play Games.');
  form.addParagraphTextItem()
    .setTitle('Messaggio che compare dopo Test')
    .setHelpText('Settings → Game window → Test. Copialo così com\'è.');
  form.addParagraphTextItem()
    .setTitle('Riga "Resize to 16:9" del log')
    .setHelpText('Settings → Logs → Open in Explorer, apri pixelchief.log e copia la riga che contiene "Resize to 16:9".');
  form.addMultipleChoiceItem()
    .setTitle('Dopo Hide game window il bot continua ad attaccare?')
    .setChoiceValues(['Sì', 'No, si ferma o vede tutto nero', 'Non l\'ho provato']);

  const bs = form.addPageBreakItem()
    .setTitle('BlueStacks')
    .setHelpText('Domande su PixelChief con BlueStacks.');
  form.addParagraphTextItem()
    .setTitle('Messaggio che compare dopo Test capture')
    .setHelpText('Settings → Test capture. Copialo così com\'è.');
  form.addTextItem()
    .setTitle('Quanto dura un attacco completo, più o meno?')
    .setHelpText('Dalla ricerca della base al ritorno al villaggio, in secondi.');
  form.addMultipleChoiceItem()
    .setTitle('Con BlueStacks ridotto a icona gli attacchi proseguono?')
    .setChoiceValues(['Sì', 'No, si fermano', 'Non l\'ho provato']);
  form.addTextItem()
    .setTitle('Versione di Android in BlueStacks')
    .setHelpText('In BlueStacks: Settings → About.');

  const fine = form.addPageBreakItem().setTitle('Com\'è andata');
  form.addParagraphTextItem()
    .setTitle('Lo Start si è fermato con un messaggio?')
    .setHelpText('Se sì, copia qui il messaggio esatto.');
  form.addParagraphTextItem().setTitle('Altro da segnalare');

  // Chi sceglie Google Play Games salta le domande su BlueStacks.
  bs.setGoToPage(fine);
  dove.setChoices([
    dove.createChoice('Google Play Games', gpg),
    dove.createChoice('BlueStacks', bs)]);

  if (form.setPublished) form.setPublished(true);  // i form nuovi possono nascere non pubblicati
  form.setAcceptingResponses(true);

  Logger.log('Link del form (da mandare per il sito): ' + form.getPublishedUrl());
  Logger.log('Link per modificare il form: ' + form.getEditUrl());
}
