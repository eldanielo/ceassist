const assistantResponsesDiv = document.getElementById('assistant-responses');
const transcriptLogDiv = document.getElementById('transcript-log');
const interimTranscriptDiv = document.getElementById('interim-transcript');
const factsList = document.getElementById('facts-list');

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'displayTranscript') {
    try {
      const data = JSON.parse(message.transcript);
      const { response_type, payload, message_id } = data;

      switch (response_type) {
        case 'TRANSCRIPT':
          interimTranscriptDiv.textContent = '';
          const entryDiv = document.createElement('div');
          entryDiv.className = 'transcript-entry message-bubble';
          entryDiv.innerHTML = payload.replace(/\n/g, '<br>');
          transcriptLogDiv.innerHTML = entryDiv.outerHTML + transcriptLogDiv.innerHTML;
          break;

        case 'INTERIM':
          interimTranscriptDiv.textContent = payload;
          break;

        case 'FACT':
        case 'TIP':
        case 'ANSWER':
          const elementId = 'gemini-' + message_id;
          let existingElement = document.getElementById(elementId);

          if (existingElement) {
            existingElement.textContent += payload;
          } else {
            if (response_type === 'FACT') {
              const factItem = document.createElement('li');
              factItem.id = elementId;
              factItem.className = 'fact-item';
              factItem.textContent = payload;
              factsList.appendChild(factItem);
            } else {
              const newElement = document.createElement('div');
              newElement.id = elementId;
              newElement.className = 'message-bubble';
              newElement.textContent = payload;
              newElement.classList.add(response_type === 'TIP' ? 'ce-tip' : 'direct-answer');
              assistantResponsesDiv.innerHTML = newElement.outerHTML + assistantResponsesDiv.innerHTML;
            }
          }
          break;
      }
    } catch (error) {
      console.error("Failed to parse incoming message:", error);
    }
  }
});
