document.getElementById('startTranscription').addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const currentTab = tabs[0];
    chrome.scripting.executeScript({
      target: { tabId: currentTab.id },
      function: () => {
        console.log('Attempting to start transcription...');
      }
    });
    // Send a message to the background script to start tab capture, including the tabId and windowId
    chrome.runtime.sendMessage({ action: 'startTabCapture', tabId: currentTab.id, windowId: currentTab.windowId });
  });
});