class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input.length > 0) {
            const pcmData = new Int16Array(input[0].length);
            for (let i = 0; i < input[0].length; i++) {
                pcmData[i] = input[0][i] * 32767;
            }
            this.port.postMessage(pcmData.buffer);
        }
        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);
