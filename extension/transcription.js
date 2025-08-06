const assistantResponsesDiv = document.getElementById('assistant-responses');
const transcriptLogDiv = document.getElementById('transcript-log');
const interimTranscriptDiv = document.getElementById('interim-transcript');
const infrastructureFactsList = document.getElementById('infrastructure-facts-list');
const otherFactsList = document.getElementById('other-facts-list');

function createExpandableElement(id, shortText, longText, baseClass, question = null) {
  const newElement = document.createElement('div');
  newElement.id = id;
  newElement.className = 'message-bubble ' + baseClass;

  const textContainer = document.createElement('div');
  
  if (question) {
    const questionDiv = document.createElement('div');
    questionDiv.style.fontWeight = 'bold';
    questionDiv.textContent = "Q: " + question;
    textContainer.appendChild(questionDiv);
  }

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

function createFactElement(id, fact, gcpService = null) {
  const factItem = document.createElement('li');
  factItem.id = id;
  factItem.className = 'fact-item';
  factItem.textContent = fact;

  if (gcpService) {
    factItem.classList.add('expandable');
    const gcpServiceDiv = document.createElement('div');
    gcpServiceDiv.className = 'gcp-service';
    gcpServiceDiv.textContent = `GCP Equivalent: ${gcpService}`;
    factItem.appendChild(gcpServiceDiv);

    factItem.addEventListener('click', (event) => {
      if (event.target !== factItem) return;
      const isExpanded = gcpServiceDiv.style.display !== 'none';
      gcpServiceDiv.style.display = isExpanded ? 'none' : 'block';
    });
  }

  return factItem;
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
            existingFactElement.firstChild.textContent += ', ' + payload.fact;
          } else {
            const factItem = createFactElement(factElementId, payload.fact, payload.gcp_service);
            if (payload.category === 'infrastructure') {
              infrastructureFactsList.appendChild(factItem);
            } else {
              otherFactsList.appendChild(factItem);
            }
          }
          break;
        case 'TIP':
          const tipElementId = 'gemini-' + message_id;
          let existingTipElement = document.getElementById(tipElementId);

          if (existingTipElement) {
            const longTextDiv = existingTipElement.querySelector('div > div:last-child');
            longTextDiv.textContent += ' ' + payload.long;
          } else {
              const newElement = createExpandableElement(
                tipElementId,
                payload.short,
                payload.long,
                'ce-tip'
              );
              assistantResponsesDiv.insertAdjacentElement('afterbegin', newElement);
          }
          break;
        case 'ANSWER':
          const answerElementId = 'gemini-' + message_id;
          let existingAnswerElement = document.getElementById(answerElementId);

          if (existingAnswerElement) {
            const longTextDiv = existingAnswerElement.querySelector('div > div:last-child');
            longTextDiv.textContent += ' ' + payload.long;
          } else {
              const newElement = createExpandableElement(
                answerElementId,
                payload.short,
                payload.long,
                'direct-answer',
                payload.question
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