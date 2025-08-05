let transcriptionTabId = null;
let websocket = null;
let offscreenDocumentCreated = false;

// Function to ensure the offscreen document is created
async function createOffscreenDocument() {
  if (offscreenDocumentCreated) return;

  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['USER_MEDIA'],
    justification: 'To capture and process audio from a tab.',
  });
  offscreenDocumentCreated = true;
  console.log('Offscreen document created.');
}

// Function to close the offscreen document
async function closeOffscreenDocument() {
  if (!offscreenDocumentCreated) return;

  await chrome.offscreen.closeDocument();
  offscreenDocumentCreated = false;
  console.log('Offscreen document closed.');
}

chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  if (message.action === 'startTabCapture') {
    // Ensure previous resources are cleaned up if any
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.close(); // This will trigger cleanup in onclose
    }
    await closeOffscreenDocument(); // Ensure offscreen is closed before starting new one

    await createOffscreenDocument();

    // Request a media stream ID from the active tab
    chrome.tabCapture.getMediaStreamId({
      targetTabId: message.tabId // Use the tabId passed from the popup
    }, async (streamId) => {
      if (!streamId) {
        console.error('Failed to get media stream ID:', chrome.runtime.lastError ? chrome.runtime.lastError.message : 'Unknown error');
        await closeOffscreenDocument(); // Clean up offscreen if streamId is not obtained
        return; // Stop execution here if streamId is null
      }

      // Send the streamId to the offscreen document to start audio capture
      chrome.runtime.sendMessage({
        target: 'offscreen',
        action: 'startAudioCapture',
        streamId: streamId
      });

      // Create a new tab to display the transcription
      chrome.tabs.create({
        url: chrome.runtime.getURL('transcription.html'),
        active: true,
        windowId: message.windowId // Use the windowId passed from the popup
      }, (newTab) => {
        if (!newTab) { // Check if newTab was successfully created
          console.error('Failed to create new transcription tab.');
          // Clean up resources if tab creation fails
          chrome.runtime.sendMessage({ target: 'offscreen', action: 'stopAudioCapture' });
          closeOffscreenDocument();
          return;
        }

        transcriptionTabId = newTab.id;
        console.log('Transcription tab created with ID:', transcriptionTabId);

        // Establish WebSocket connection to the backend
        websocket = new WebSocket('ws://localhost:8000/ws/transcribe'); // Adjust if your backend is on a different host/port

        websocket.onopen = () => {
          console.log('WebSocket connected.');
        };

        websocket.onmessage = (event) => {
          // Send the transcribed text to the transcription tab
          if (transcriptionTabId) {
            chrome.tabs.sendMessage(transcriptionTabId, { action: 'displayTranscript', transcript: event.data });
          }
        };

        websocket.onclose = () => {
          console.log('WebSocket disconnected.');
          // Tell offscreen document to stop audio capture and clean up
          chrome.runtime.sendMessage({ target: 'offscreen', action: 'stopAudioCapture' });
          closeOffscreenDocument();
          // Reset transcriptionTabId
          transcriptionTabId = null;
        };

        websocket.onerror = (error) => {
          console.error('WebSocket error:', error);
          // Tell offscreen document to stop audio capture and clean up
          chrome.runtime.sendMessage({ target: 'offscreen', action: 'stopAudioCapture' });
          closeOffscreenDocument();
          // Reset transcriptionTabId
          transcriptionTabId = null;
        };
      });
    });
  } else if (message.action === 'audioChunk') {
    // Receive audio chunks from the offscreen document and send to WebSocket
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      // Convert the plain array back to a typed array before sending
      const int16Array = new Int16Array(message.chunk);
      console.log('Background: Received audio chunk from offscreen, sending to WebSocket.'); // Debug print
      websocket.send(int16Array.buffer);
    } else {
      console.warn('Background: WebSocket not open, dropping audio chunk.');
    }
  } else if (message.action === 'error' && message.target === 'offscreen') {
    console.error('Error from offscreen document:', message.message);
    // Handle error, e.g., close WebSocket, notify user
    if (websocket) {
      websocket.close();
    }
    closeOffscreenDocument();
  }
});