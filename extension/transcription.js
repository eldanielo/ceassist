chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'displayTranscript') {
    const transcriptDiv = document.getElementById('transcript');
    if (transcriptDiv) {
      transcriptDiv.textContent += message.transcript + '\n';
      transcriptDiv.scrollTop = transcriptDiv.scrollHeight; // Auto-scroll to bottom
    }
  }
});