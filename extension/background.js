let transcriptionTabId = null;
let websocket = null;

async function hasOffscreenDocument() {
    return await chrome.offscreen.hasDocument();
}

async function createOffscreenDocument() {
  if (await hasOffscreenDocument()) return;

  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
    justification: 'To capture tab audio for transcription and play it back.',
  });
}

async function closeOffscreenDocument() {
  if (!await hasOffscreenDocument()) return;
  await chrome.offscreen.closeDocument();
}

chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  if (message.action === 'startTabCapture') {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.close();
    }
    await closeOffscreenDocument();
    await createOffscreenDocument();

    chrome.tabCapture.getMediaStreamId({
      targetTabId: message.tabId
    }, async (streamId) => {
      if (!streamId) {
        console.error('Failed to get media stream ID:', chrome.runtime.lastError ? chrome.runtime.lastError.message : 'Unknown error');
        await closeOffscreenDocument();
        return;
      }

      chrome.runtime.sendMessage({
        target: 'offscreen',
        action: 'startAudioCapture',
        streamId: streamId
      });

      chrome.tabs.create({
        url: chrome.runtime.getURL('transcription.html'),
        active: true,
        windowId: message.windowId
      }, (newTab) => {
        transcriptionTabId = newTab.id;
        websocket = new WebSocket('wss://ceassist-668228315581.us-central1.run.app/ws/transcribe');

        websocket.onopen = () => console.log('WebSocket connected.');
        websocket.onmessage = (event) => {
          if (transcriptionTabId) {
            chrome.runtime.sendMessage({ action: 'displayTranscript', transcript: event.data });
          }
        };
        websocket.onclose = () => {
          console.log('WebSocket disconnected.');
          chrome.runtime.sendMessage({ target: 'offscreen', action: 'stopAudioCapture' });
          transcriptionTabId = null;
        };
        websocket.onerror = (error) => {
          console.error('WebSocket error:', error);
          websocket.close();
        };
      });
    });
  } else if (message.action === 'audioChunk') {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      const int16Array = new Int16Array(message.chunk);
      websocket.send(int16Array.buffer);
    }
  } else if (message.action === 'error' && message.target === 'offscreen') {
    console.error('Error from offscreen document:', message.message);
    if (websocket) websocket.close();
    await closeOffscreenDocument();
  }
});