// Recorder.js: https://github.com/mattdiamond/Recorderjs (versión compacta)
(function(window){
  var WORKER_PATH = '';
  var Recorder = function(source, cfg){
    var config = cfg || {};
    var bufferLen = config.bufferLen || 4096;
    this.context = source.context;
    // Forzar mono en la inicialización del ScriptProcessorNode
    if(!this.context.createScriptProcessor)
      this.node = this.context.createJavaScriptNode(bufferLen, 1, 1);
    else
      this.node = this.context.createScriptProcessor(bufferLen, 1, 1);
    var recording = false,
      currCallback;
    this.node.onaudioprocess = function(e){
      if(!recording) return;
      // Solo canal 0 para grabación mono
      var input = e.inputBuffer.getChannelData(0);
      // Clonar el buffer para evitar referencias
      var buffer = new Float32Array(input.length);
      buffer.set(input);
      window.Recorder.forceBuffer.push([buffer]);
    };
    this.record = function(){ recording = true; };
    this.stop = function(){ recording = false; };
    this.clear = function(){ window.Recorder.forceBuffer = []; };
    this.exportWAV = function(cb, type){
      var buffers = window.Recorder.forceBuffer;
      // Sin detección de silencio: exporta y envía todos los fragmentos
      var totalSamples = buffers.reduce((acc, b) => acc + b[0].length, 0);
      if (!buffers.length || totalSamples === 0) {
        // Buffer realmente vacío
        cb(new Blob([], { type: type || 'audio/wav' }));
        return;
      }
      var dataview = window.Recorder.encodeWAV(buffers, 1, this.context.sampleRate); // Exportar como mono
      var audioBlob = new Blob([dataview], { type: type || 'audio/wav' });
      cb(audioBlob);
    };
    source.connect(this.node);
    this.node.connect(this.context.destination);
  };
  window.Recorder = Recorder;
  window.Recorder.forceBuffer = [];
  window.Recorder.encodeWAV = function(buffers, numChannels, sampleRate){
    // Ajustar para siempre exportar como mono
    var length = buffers.length * buffers[0][0].length * 2;
    var buffer = new ArrayBuffer(44 + length);
    var view = new DataView(buffer);
    function writeString(view, offset, string){
      for (var i = 0; i < string.length; i++){
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    }
    var offset = 0;
    writeString(view, offset, 'RIFF'); offset += 4;
    view.setUint32(offset, 36 + length, true); offset += 4;
    writeString(view, offset, 'WAVE'); offset += 4;
    writeString(view, offset, 'fmt '); offset += 4;
    view.setUint32(offset, 16, true); offset += 4;
    view.setUint16(offset, 1, true); offset += 2;
    view.setUint16(offset, 1, true); offset += 2; // Mono
    view.setUint32(offset, sampleRate, true); offset += 4;
    view.setUint32(offset, sampleRate * 2, true); offset += 4;
    view.setUint16(offset, 2, true); offset += 2;
    view.setUint16(offset, 16, true); offset += 2;
    writeString(view, offset, 'data'); offset += 4;
    view.setUint32(offset, length, true); offset += 4;
    for(var i = 0; i < buffers.length; i++){
      var input = buffers[i][0]; // Solo canal 0
      for(var j = 0; j < input.length; j++){
        var s = Math.max(-1, Math.min(1, input[j]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        offset += 2;
      }
    }
    return view;
  };
})(window);
