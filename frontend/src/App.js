import React, { useState, useRef } from 'react';
import axios from 'axios';
import { Mic, StopCircle, Copy, Loader2 } from 'lucide-react';

import { Button } from './components/ui/button.jsx';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card.jsx';
import { Textarea } from './components/ui/textarea.jsx';
import { Alert, AlertDescription, AlertTitle } from './components/ui/alert.jsx';

const App = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState('');

  // Refs for audio processing
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const dataArrayRef = useRef(null);
  const sourceRef = useRef(null);
  const animationFrameIdRef = useRef(null);
  const canvasRef = useRef(null);

  const API_URL = 'http://127.0.0.1:8000/transcribe/';

  const drawWaveform = () => {
    if (!analyserRef.current || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const canvasCtx = canvas.getContext('2d');
    const bufferLength = analyserRef.current.frequencyBinCount;

    analyserRef.current.getByteFrequencyData(dataArrayRef.current);

    canvasCtx.fillStyle = 'rgb(241, 245, 249)'; // bg-slate-100
    canvasCtx.fillRect(0, 0, canvas.width, canvas.height);

    const barWidth = (canvas.width / bufferLength) * 2.5;
    let barHeight;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      barHeight = dataArrayRef.current[i];
      canvasCtx.fillStyle = `rgb(59, 130, 246)`; // bg-blue-500
      canvasCtx.fillRect(x, canvas.height - barHeight / 2, barWidth, barHeight / 2);
      x += barWidth + 1;
    }

    animationFrameIdRef.current = requestAnimationFrame(drawWaveform);
  };

  const handleStartRecording = async () => {
    setError('');
    setTranscript('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Setup for MediaRecorder
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mediaRecorderRef.current.ondataavailable = (event) => audioChunksRef.current.push(event.data);
      mediaRecorderRef.current.onstop = () => handleTranscription();
      mediaRecorderRef.current.start();
      setIsRecording(true);

      // Setup for Web Audio API visualization
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      dataArrayRef.current = new Uint8Array(analyserRef.current.frequencyBinCount);
      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);
      sourceRef.current.connect(analyserRef.current);

      // Start drawing
      animationFrameIdRef.current = requestAnimationFrame(drawWaveform);

    } catch (err) {
      console.error('Error starting recording:', err);
      setError('Could not start recording. Please ensure microphone permissions are enabled.');
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      
      // Stop media stream tracks
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
      
      // Cleanup Web Audio API resources
      cancelAnimationFrame(animationFrameIdRef.current);
      sourceRef.current?.disconnect();
      audioContextRef.current?.close();

      // Clear canvas
      const canvas = canvasRef.current;
      if (canvas) {
        const canvasCtx = canvas.getContext('2d');
        canvasCtx.fillStyle = 'rgb(241, 245, 249)';
        canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
      }
    }
  };

  const handleTranscription = async () => {
    setIsTranscribing(true);
    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
    const audioFile = new File([audioBlob], 'recording.webm', { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('file', audioFile);

    try {
      const response = await axios.post(API_URL, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTranscript(response.data.transcript);
    } catch (err) {
      console.error('Error transcribing audio:', err);
      setError('Failed to transcribe audio. Please check the backend server and try again.');
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(transcript).catch(err => console.error('Failed to copy text:', err));
  };

  return (
    <div className="bg-slate-100 text-slate-900 min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl shadow-lg">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold">Speech-to-Text Tool</CardTitle>
          <CardDescription>Click record, speak, and let the AI do the rest.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center space-y-6">
            <canvas ref={canvasRef} width="500" height="100" className="rounded-lg bg-slate-200"></canvas>

            <div className="flex items-center space-x-4">
              {!isRecording ? (
                <Button onClick={handleStartRecording} disabled={isTranscribing} size="lg">
                  <Mic className="mr-2 h-5 w-5" />
                  Start Recording
                </Button>
              ) : (
                <Button onClick={handleStopRecording} variant="destructive" size="lg">
                  <StopCircle className="mr-2 h-5 w-5" />
                  Stop Recording
                </Button>
              )}
            </div>

            {isTranscribing && (
              <div className="flex items-center text-slate-500">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                <span>Transcribing, please wait...</span>
              </div>
            )}

            {error && (
              <Alert variant="destructive">
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {transcript && (
              <div className="relative w-full pt-4">
                <Textarea
                  readOnly
                  value={transcript}
                  className="h-48 text-base bg-white"
                  placeholder="Your transcript will appear here..."
                />
                <Button
                  size="icon"
                  variant="ghost"
                  className="absolute top-6 right-2"
                  onClick={handleCopy}
                >
                  <Copy className="h-5 w-5" />
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default App;



