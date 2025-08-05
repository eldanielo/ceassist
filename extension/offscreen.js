let audioContext = null;
let mediaStreamSource = null;
let scriptProcessor = null;
let mediaStream = null;

chrome.runtime.onMessage.addListener(async (message) => {
  if (message.action === 'startAudioCapture') {
    const streamId = message.streamId;

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } },
        video: false
      });
      
      // Play the captured audio
      const audio = new Audio();
      audio.srcObject = mediaStream;
      audio.play();

      // Set up audio processing for transcription
      audioContext = new AudioContext();
      mediaStreamSource = audioContext.createMediaStreamSource(mediaStream);
      scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

      scriptProcessor.onaudioprocess = (event) => {
        const inputBuffer = event.inputBuffer.getChannelData(0);
        const int16Array = new Int16Array(inputBuffer.length);
        for (let i = 0; i < inputBuffer.length; i++) {
          int16Array[i] = Math.min(1, Math.max(-1, inputBuffer[i])) * 0x7FFF;
        }
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
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
    if (scriptProcessor) scriptProcessor.disconnect();
    if (mediaStreamSource) mediaStreamSource.disconnect();
    if (audioContext) audioContext.close();
    console.log('Offscreen: Audio capture stopped and resources released.');
  }
});