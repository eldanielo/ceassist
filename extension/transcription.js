const assistantResponsesDiv = document.getElementById('assistant-responses');
const transcriptLogDiv = document.getElementById('transcript-log');
const interimTranscriptDiv = document.getElementById('interim-transcript');
const factsList = document.getElementById('facts-list');

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'displayTranscript') {
    const text = message.transcript;

    if (text.startsWith('COACH:')) {
      const parts = text.substring(7).split(':');
      const messageId = parts[0];
      const contentChunk = parts.slice(1).join(':');
      
      const messageElementId = 'coach-' + messageId;
      let existingElement = document.getElementById(messageElementId);

      if (existingElement) {
        // If the element already exists, just append the new text.
        // This works whether it's a fact or a regular message.
        existingElement.textContent += contentChunk;
      } else {
        // This is the first chunk for a new message.
        // We need to decide where to create the element.
        const trimmedContent = contentChunk.trim();

        if (trimmedContent.startsWith('FACT:')) {
          // It's a fact. Create it ONLY in the facts list.
          const factText = trimmedContent.substring(5).trim();
          const factItem = document.createElement('li');
          factItem.id = messageElementId; // Assign the unique ID
          factItem.className = 'fact-item';
          factItem.textContent = factText;
          factsList.appendChild(factItem);
        } else {
          // It's a regular coach response. Create it in the assistant panel.
          const newElement = document.createElement('div');
          newElement.id = messageElementId; // Assign the unique ID
          newElement.className = 'message-bubble';
          newElement.textContent = contentChunk;

          if (trimmedContent.startsWith('💡 CE Tip:')) {
            newElement.classList.add('ce-tip');
          } else {
            newElement.classList.add('direct-answer');
          }
          
          assistantResponsesDiv.innerHTML = newElement.outerHTML + assistantResponsesDiv.innerHTML;
        }
      }

    } else if (text.startsWith('TRANSCRIPT:')) {
      interimTranscriptDiv.textContent = '';
      const transcriptText = text.substring(11);
      
      const entryDiv = document.createElement('div');
      entryDiv.className = 'transcript-entry message-bubble';
      entryDiv.innerHTML = transcriptText.replace(/\n/g, '<br>');
      
      transcriptLogDiv.innerHTML = entryDiv.outerHTML + transcriptLogDiv.innerHTML;

    } else if (text.startsWith('INTERIM:')) {
      const interimText = text.substring(9);
      interimTranscriptDiv.textContent = interimText;
    }
  }
});