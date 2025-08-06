const assistantResponsesDiv = document.getElementById('assistant-responses');
const transcriptLogDiv = document.getElementById('transcript-log');
const interimTranscriptDiv = document.getElementById('interim-transcript');
const factsList = document.getElementById('facts-list');

function createExpandableElement(id, shortText, longText, baseClass) {
  const newElement = document.createElement('div');
  newElement.id = id;
  newElement.className = 'message-bubble ' + baseClass;

  const textContainer = document.createElement('div');
  
  const shortTextDiv = document.createElement('div');
  shortTextDiv.textContent = shortText;
  
  const longTextDiv = document.createElement('div');
  longTextDiv.textContent = longText;
  longTextDiv.style.display = 'none';
  
  textContainer.appendChild(shortTextDiv);
  textContainer.appendChild(longTextDiv);

  const arrow = document.createElement('span');
  arrow.className = 'arrow';

  newElement.appendChild(textContainer);
  newElement.appendChild(arrow);

  newElement.addEventListener('click', () => {
    const isExpanded = longTextDiv.style.display !== 'none';
    longTextDiv.style.display = isExpanded ? 'none' : 'block';
    arrow.classList.toggle('expanded', !isExpanded);
  });

  return newElement;
}

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
          transcriptLogDiv.insertAdjacentElement('afterbegin', entryDiv);
          break;

        case 'INTERIM':
          interimTranscriptDiv.textContent = payload;
          break;

        case 'FACT':
          const factElementId = 'gemini-fact-' + message_id;
          let existingFactElement = document.getElementById(factElementId);
          if (existingFactElement) {
            existingFactElement.textContent += ', ' + payload.fact;
          } else {
            const factItem = document.createElement('li');
            factItem.id = factElementId;
            factItem.className = 'fact-item';
            factItem.textContent = payload.fact;
            factsList.appendChild(factItem);
          }
          break;
        case 'TIP':
        case 'ANSWER':
          const elementId = 'gemini-' + message_id;
          let existingElement = document.getElementById(elementId);

          if (existingElement) {
            const longTextDiv = existingElement.querySelector('div > div:last-child');
            longTextDiv.textContent += ' ' + payload.long;
          } else {
              const newElement = createExpandableElement(
                elementId,
                payload.short,
                payload.long,
                response_type === 'TIP' ? 'ce-tip' : 'direct-answer'
              );
              assistantResponsesDiv.insertAdjacentElement('afterbegin', newElement);
          }
          break;
      }
    } catch (error) {
      console.error("Failed to parse incoming message:", error);
    }
  }
});

// Inform the background script that the transcription window is ready.
chrome.runtime.sendMessage({ action: 'transcriptionWindowReady' });