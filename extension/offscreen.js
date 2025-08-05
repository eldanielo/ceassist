let audioContext = null;
let mediaStreamSource = null;
let scriptProcessor = null;
let mediaStream = null;

chrome.runtime.onMessage.addListener(async (message) => {
  if (message.action === 'startAudioCapture') {
    const streamId = message.streamId;
    console.log('Offscreen: Received startAudioCapture with streamId:', streamId);

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } },
        video: false
      });
      console.log('Offscreen: MediaStream obtained successfully.', mediaStream);

      audioContext = new AudioContext();
      // console.log('Offscreen: AudioContext sample rate:', audioContext.sampleRate); // Removed debug print

      mediaStreamSource = audioContext.createMediaStreamSource(mediaStream);
      scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

      scriptProcessor.onaudioprocess = (event) => {
        // This log will fire repeatedly if audio is being processed
        // console.log('Offscreen: onaudioprocess triggered, sending audio chunk.'); // Keep this commented for cleaner output
        const inputBuffer = event.inputBuffer.getChannelData(0);
        const int16Array = new Int16Array(inputBuffer.length);
        for (let i = 0; i < inputBuffer.length; i++) {
          int16Array[i] = Math.min(1, Math.max(-1, inputBuffer[i])) * 0x7FFF;
        }
        // Convert buffer to a plain array to send via message
        const chunkArray = Array.from(new Int16Array(int16Array.buffer));
        chrome.runtime.sendMessage({ action: 'audioChunk', chunk: chunkArray });
      };

      mediaStreamSource.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);

    } catch (error) {
      console.error('Offscreen: Error getting MediaStream:', error);
      chrome.runtime.sendMessage({ action: 'error', message: error.message });
    }
  } else if (message.action === 'stopAudioCapture') {
    if (scriptProcessor) {
      scriptProcessor.disconnect();
      scriptProcessor = null;
    }
    if (mediaStreamSource) {
      mediaStreamSource.disconnect();
      mediaStreamSource = null;
    }
    if (audioContext) {
      audioContext.close();
      audioContext = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
    console.log('Offscreen: Audio capture stopped and resources released.');
  }
});