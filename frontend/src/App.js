import React, { useState, useRef } from 'react';
import axios from 'axios';
import { Mic, StopCircle, Copy, Loader2, Upload, Download } from 'lucide-react';

import { Button } from './components/ui/button.jsx';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card.jsx';
import { Textarea } from './components/ui/textarea.jsx';
import { Alert, AlertDescription, AlertTitle } from './components/ui/alert.jsx';

const App = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [srtTranscript, setSrtTranscript] = useState('');
  const [error, setError] = useState('');
  const [uploadedFile, setUploadedFile] = useState(null);

  // Refs for audio processing
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const dataArrayRef = useRef(null);
  const sourceRef = useRef(null);
  const animationFrameIdRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);

  const API_URL = 'http://127.0.0.1:8000/transcribe/';
  const DOWNLOAD_TEXT_URL = 'http://127.0.0.1:8000/download-transcript/';
  const DOWNLOAD_SRT_URL = 'http://127.0.0.1:8000/download-srt/';

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
    setSrtTranscript('');
    setUploadedFile(null);
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
    await transcribeFile(audioFile);
  };

  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file) {
      // Check if it's an audio file
      if (!file.type.startsWith('audio/')) {
        setError('Please upload a valid audio file (mp3, wav, m4a, etc.)');
        return;
      }
      setUploadedFile(file);
      setError('');
      setTranscript('');
      setSrtTranscript('');
    }
  };

  const handleUploadTranscription = async () => {
    if (!uploadedFile) {
      setError('Please select an audio file first');
      return;
    }
    await transcribeFile(uploadedFile);
  };

  const transcribeFile = async (audioFile) => {
    setIsTranscribing(true);
    const formData = new FormData();
    formData.append('file', audioFile);

    try {
      const response = await axios.post(API_URL, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTranscript(response.data.transcript);
      setSrtTranscript(response.data.srt_transcript);
    } catch (err) {
      console.error('Error transcribing audio:', err);
      setError('Failed to transcribe audio. Please check the backend server and try again.');
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleDownloadText = async () => {
    try {
      const response = await axios.post(
        DOWNLOAD_TEXT_URL,
        { transcript },
        { 
          responseType: 'blob',
          headers: { 'Content-Type': 'application/json' }
        }
      );
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'transcript.txt');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Error downloading transcript:', err);
      setError('Failed to download transcript file.');
    }
  };

  const handleDownloadSRT = async () => {
    try {
      const response = await axios.post(
        DOWNLOAD_SRT_URL,
        { srt_transcript: srtTranscript },
        { 
          responseType: 'blob',
          headers: { 'Content-Type': 'application/json' }
        }
      );
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'subtitles.srt');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Error downloading SRT:', err);
      setError('Failed to download SRT file.');
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
          <CardDescription>Record audio or upload a file to get AI-powered transcription</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center space-y-6">
            {/* Recording Section */}
            <div className="w-full border-b pb-6">
              <h3 className="text-lg font-semibold mb-4 text-center">Record Audio</h3>
              <canvas ref={canvasRef} width="500" height="100" className="rounded-lg bg-slate-200 mx-auto mb-4"></canvas>

              <div className="flex items-center justify-center space-x-4">
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
            </div>

            {/* File Upload Section */}
            <div className="w-full border-b pb-6">
              <h3 className="text-lg font-semibold mb-4 text-center">Upload Audio File</h3>
              <div className="flex flex-col items-center space-y-4">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept="audio/*"
                  className="hidden"
                />
                <Button 
                  onClick={() => fileInputRef.current?.click()} 
                  disabled={isTranscribing || isRecording}
                  variant="outline"
                  size="lg"
                >
                  <Upload className="mr-2 h-5 w-5" />
                  Choose Audio File
                </Button>
                
                {uploadedFile && (
                  <div className="text-center">
                    <p className="text-sm text-slate-600 mb-2">Selected: {uploadedFile.name}</p>
                    <Button 
                      onClick={handleUploadTranscription} 
                      disabled={isTranscribing}
                      variant="outline"
                      size="lg"
                    >
                      {isTranscribing ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Transcribing...
                        </>
                      ) : (
                        'Transcribe File'
                      )}
                    </Button>
                  </div>
                )}
              </div>
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
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-lg font-semibold">Transcript</h3>
                  <div className="flex space-x-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleCopy}
                    >
                      <Copy className="h-4 w-4 mr-1" />
                      Copy
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleDownloadText}
                    >
                      <Download className="h-4 w-4 mr-1" />
                      Download TXT
                    </Button>
                    {srtTranscript && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleDownloadSRT}
                      >
                        <Download className="h-4 w-4 mr-1" />
                        Download SRT
                      </Button>
                    )}
                  </div>
                </div>
                <Textarea
                  readOnly
                  value={transcript}
                  className="h-48 text-base bg-white"
                  placeholder="Your transcript will appear here..."
                />
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default App;



