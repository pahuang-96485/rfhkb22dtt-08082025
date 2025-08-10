//voice-capture.tsx
"use client";
// Extend WavStreamPlayer to include speakText()
declare module '../lib/wavtools/index.js' {
  interface WavStreamPlayer {
    speakText(text: string): void;
  }
}
import { useState, useRef, useEffect, useCallback } from 'react';
import { WavRecorder, WavStreamPlayer} from '../lib/wavtools/index.js';
import { WavRenderer } from '../utils/wav_renderer';
import { RealtimeClient } from '@openai/realtime-api-beta';
import { Avatar } from "./avatar";
import { useAuth } from "../auth/AuthContext";

interface ItemType {
  id: string;
  role?: string;
  type?: string;
  formatted: {
    output?: string;
    tool?: {
      name: string;
      arguments: string;
    };
    transcript?: string;
    audio?: { length: number };
    text?: string;
    file?: {
      url: string;
    };
  };
}

interface VoiceCaptureProps {
  onClose: () => void;
}




export default function VoiceCapture({ onClose }: VoiceCaptureProps) {
  // --- Begin: Realtime API with VAD Integration ---
  const { user } = useAuth();  // Get current user
  if (!user) {
    return <div>Loading user information…</div>;  // Show while user data is loading
  }

  const token = user.token;

  const [sessionId, setSessionId] = useState<string>(() => {
    const saved = localStorage.getItem("session_id");
    if (saved) return saved;
    const newId = crypto.randomUUID();
    localStorage.setItem("session_id", newId);
    return newId;
  });


    useEffect(() => {
      if (process.env.NODE_ENV === 'development') {
        const originalFetch = window.fetch;

        window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
 
          const getUrlString = (input: RequestInfo | URL): string => {
            if (typeof input === 'string') return input;
            if (input instanceof URL) return input.href;
            if ('url' in input) return input.url; 
            return String(input); 
          };

          const url = getUrlString(input);


          console.log('[FETCH DEBUG]', {
            url,
            method: init?.method || 'GET',
            headers: init?.headers,
            body: init?.body ? await parseBody(init.body) : null
          });

          return originalFetch(input, init);
        };


        const parseBody = async (body: BodyInit): Promise<any> => {
          if (typeof body === 'string') {
            try {
              return JSON.parse(body);
            } catch {
              return body;
            }
          }
          return '<non-string-body>';
        };

        return () => {
          window.fetch = originalFetch;
        };
      }
    }, []);

  /**
   * Instantiate:
   * - WavRecorder (speech input)
   * - WavStreamPlayer (speech output)
   * - RealtimeClient (API client)
   */
    const wavRecorderRef = useRef<WavRecorder>(
        new WavRecorder({ sampleRate: 24000 })
      );

    const wavStreamPlayerRef = useRef<WavStreamPlayer>(
        new WavStreamPlayer({ sampleRate: 24000 })
     );

    const clientRef = useRef<RealtimeClient>(
        // new RealtimeClient({
        //    url: process.env.NEXT_PUBLIC_RELAY_SERVER_URL
        // })

        // If not use relay server, use this:
         new RealtimeClient({
             apiKey: process.env.NEXT_PUBLIC_OPENAI_API_KEY!,
             dangerouslyAllowAPIKeyInBrowser: true,
         })
    );

    const client = clientRef.current;
    client.updateSession({
        turn_detection : { type: 'server_vad' },
    });


    /**
     * References for
     * - Rendering audio visualization (canvas)
     * - Autoscrolling event logs
     * - Timing delta for event log displays
     */
    const clientCanvasRef = useRef<HTMLCanvasElement>(null);
    const serverCanvasRef = useRef<HTMLCanvasElement>(null);
    const startTimeRef = useRef<string>(new Date().toISOString());
    
    /**
     * All of variables for displaying application state
     * - items are all conversation items (dialog)
     * - memoryKv is for set_memory() function
     */
    const [expandedEvents, setExpandedEvents] = useState<{
        [key: string]: boolean;
    }>({});
    const [items, setItems] = useState<ItemType[]>([]);
    const [memoryKv, setMemoryKv] = useState<{ [key: string]: any }>({});
    const [isConnected, setIsConnected] = useState(false);
    const hasConnectedRef = useRef(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = useCallback(() => {
      if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
      }
    }, []);

    useEffect(() => {
      scrollToBottom();
    }, [items, scrollToBottom]);

    /**
     * Connect to conversation:
     * WavRecorder taks speech input, WavStreamPlayer output, client is API client
     */
    const connectConversation = useCallback(async () => {
        const client = clientRef.current;
        const wavRecorder = wavRecorderRef.current;
        const wavStreamPlayer = wavStreamPlayerRef.current;

        // Set state variables
        startTimeRef.current = new Date().toISOString();
        setIsConnected(true);
        setItems(client.conversation.getItems());

        // Connect to microphone
        await wavRecorder.begin();

        // Connect to audio output
        await wavStreamPlayer.connect();

        // Connect to realtime API
        await client.connect();


        if (!clientRef.current?.isConnected()) {
          console.warn("Realtime client is not connected");
          return;
        }

        client.sendUserMessageContent([
        {
            type: `input_text`,
            text: `Hello`,
        },
        ]);
        
        // Start capturing microphone input and forward each audio chunk to the Realtime API
        await wavRecorder.record((data) => client.appendInputAudio(data.mono));

    }, []);

    /**
     * Disconnect and reset conversation state
     */
    const disconnectConversation = useCallback(async () => {
        setIsConnected(false);
        setItems([]);
        setMemoryKv({});

        const client = clientRef.current;
        client.disconnect();

        const wavRecorder = wavRecorderRef.current;
        await wavRecorder.end();

        const wavStreamPlayer = wavStreamPlayerRef.current;
        await wavStreamPlayer.interrupt();

        // Call onClose to return to text input
        onClose();
    }, [onClose]);

    const deleteConversationItem = useCallback(async (id: string) => {
        const client = clientRef.current;
        client.deleteItem(id);
    }, []);

    
    /**
     * Set up render loops for the visualization canvas
     */
    useEffect(() => {
        let isLoaded = true;

        const wavRecorder = wavRecorderRef.current;
        const clientCanvas = clientCanvasRef.current;
        let clientCtx: CanvasRenderingContext2D | null = null;

        const wavStreamPlayer = wavStreamPlayerRef.current;
        const serverCanvas = serverCanvasRef.current;
        let serverCtx: CanvasRenderingContext2D | null = null;

        const render = () => {
        if (isLoaded) {
            if (clientCanvas) {
            if (!clientCanvas.width || !clientCanvas.height) {
                clientCanvas.width = clientCanvas.offsetWidth;
                clientCanvas.height = clientCanvas.offsetHeight;
            }
            clientCtx = clientCtx || clientCanvas.getContext('2d');
            if (clientCtx) {
                clientCtx.clearRect(0, 0, clientCanvas.width, clientCanvas.height);
                const result = wavRecorder.recording
                ? wavRecorder.getFrequencies('voice')
                : { values: new Float32Array([0]) };
                WavRenderer.drawBars(
                clientCanvas,
                clientCtx,
                result.values,
                '#0099ff',
                10,
                0,
                8
                );
            }
            }
            if (serverCanvas) {
            if (!serverCanvas.width || !serverCanvas.height) {
                serverCanvas.width = serverCanvas.offsetWidth;
                serverCanvas.height = serverCanvas.offsetHeight;
            }
            serverCtx = serverCtx || serverCanvas.getContext('2d');
            if (serverCtx) {
                serverCtx.clearRect(0, 0, serverCanvas.width, serverCanvas.height);
                const result = wavStreamPlayer.analyser
                ? wavStreamPlayer.getFrequencies('voice')
                : { values: new Float32Array([0]) };
                WavRenderer.drawBars(
                serverCanvas,
                serverCtx,
                result.values,
                '#009900',
                10,
                0,
                8
                );
            }
            }
            window.requestAnimationFrame(render);
        }
        };
        render();

        return () => {
        isLoaded = false;
        };
    }, []);

  /**
   * Core RealtimeClient and audio capture setup
   * Set all of our instructions, tools, events and more
   */
  useEffect(() => {
    // Get refs
    const wavStreamPlayer = wavStreamPlayerRef.current;
    const client = clientRef.current;

    // ------------------- Modification -------------------------
    // Set instructions 
    const fname = (user as any)?.fname || "";
    const welcome = fname 
      ? `Hi ${fname}, I'm your assistant. How can I help you today?`
      : `Hi there, I'm your assistant. How can I help you today?`;

    const instructions = `
      You are a medical assistant. When starting a new session, greet the user with: 
      "${welcome}"

      Follow these instructions carefully:
      - Keep each response under 50 words.
      - Be polite, professional, and concise.
      - Do NOT fabricate or guess.

      Scheduling:
      - Use the 'chat_voice' tool if the user (either a doctor or a patient) mentions anything about appointments, booking, canceling, rescheduling, or managing availability.
      - Doctor-specific actions such as creating an event, reactivating a slot, or cancelling a time slot are also scheduling actions.
      - When 'chat_voice' is called, return the 'reply' field exactly as-is.
      - Do NOT paraphrase, reword, or summarize the reply. Just return it or read it out loud.
      - Do not interpret the returned 'available_slots', just pass through.

      General Chat:
      - If the question is not about schedule, answer it directly without using any tool.
      - You may respond briefly to casual conversation (e.g. "how are you", "what’s your name") in a friendly way.

      Session Behavior:
      - If the user greets you or opens a new session, you may introduce yourself briefly as an AI assistant for scheduling and simple medical questions.
      `
      ;

    // ----------------------------------------------------------

    // Configure session: set instructions and enable Whisper transcription
    client.updateSession({
      instructions,
      input_audio_transcription: { model: "whisper-1" }
    });

    // Add tools
    client.addTool(
      {
        name: 'set_memory',
        description: 'Saves important data about the user into memory.',
        parameters: {
          type: 'object',
          properties: {
            key: {
              type: 'string',
              description:
                'The key of the memory value. Always use lowercase and underscores, no other characters.',
            },
            value: {
              type: 'string',
              description: 'Value can be anything represented as a string',
            },
          },
          required: ['key', 'value'],
        },
      },
      async ({ key, value }: { [key: string]: any }) => {
        setMemoryKv((memoryKv) => {
          const newKv = { ...memoryKv };
          newKv[key] = value;
          return newKv;
        });
        return { ok: true };
      }
    );
    



    // ----------------------- Start: New Schedule Module -----------------------
    // use a unified payload to pass a complete object at runtime.
    // The backend will unpack, validate, and dispatch based on `tool`.
    client.addTool(
      {
        name: 'chat_voice',
        description: 'Triggers backend /chat/voice for processing user speech',
        parameters: {
          type: 'object',
          properties: {
            message: {
              type: 'string',
              description: 'Full user utterance (transcribed text)',
            },
            session_id: {
              type: 'string',
            }
          },
          required: ['message', 'session_id'],
        },
      },
      async ({ message }: { message: string }) => {

        console.groupCollapsed('[chat_voice] Request Debug');
        console.log('Endpoint:', '/chat/voice');
        console.log('Token:', token.substring(0, 5) + '...');
        console.log('Payload:', {
          message,
          context: {
            session_id: sessionId,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            input_mode: "voice"
          }
        });
        console.groupEnd();


        try {
          const response = await fetch("/chat/voice", {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              message,
              context: {
                session_id: sessionId,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                input_mode: "voice"
              }
            }),
          });

          if (!response.ok) {
            const errorData = await response.json();
            console.error("[ERROR] Backend response:", errorData);
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          return await response.json();
        } catch (error) {
          console.error("[ERROR] Failed to call /chat/voice:", error);
          throw error;
        }
      }
    );


  // ----------------------- End: New Schedule Module ----------------------
  
  
    client.on('error', (event: any) => console.error(event));
    client.on('conversation.interrupted', async () => {
      const trackSampleOffset = await wavStreamPlayer.interrupt();
      if (trackSampleOffset?.trackId) {
        const { trackId, offset } = trackSampleOffset;
        await client.cancelResponse(trackId, offset);
      }
    });
    client.on('conversation.updated', async ({ item, delta }: any) => {
      const items = client.conversation.getItems();
      if (delta?.audio) {
        wavStreamPlayer.add16BitPCM(delta.audio, item.id);
      }
      if (item.status === 'completed' && item.formatted.audio?.length) {
        const wavFile = await WavRecorder.decode(
          item.formatted.audio,
          24000,
          24000
        );
        item.formatted.file = wavFile;
      }
      setItems(items);
    });

    setItems(client.conversation.getItems());

    return () => {
      // cleanup; resets to defaults
      client.reset();
    };
  }, []);

  useEffect(() => {
    if (!hasConnectedRef.current) {
      hasConnectedRef.current = true;
      connectConversation();
    }
  }, [connectConversation]);

  return (
    <div className="flex flex-col h-[550px] sm:h-[750px]">
      <div className="flex-grow overflow-y-auto p-2 sm:p-4">
        <div className="content-block conversation">
          <div className="content-block-body space-y-6 py-2" data-conversation-content>
            {!items.length && "awaiting connection..."}
            {items
              // Skip the very first user message if needed
              .filter((item, index) => !(index === 0 && item.role === "user"))
              
              .filter(item => {
                
                return item.formatted.text || item.formatted.transcript;
              })
              
              .map((conversationItem) => {
                return (
                  <div
                    className="flex gap-3 my-4 text-gray-600 text-sm flex-1"
                    key={conversationItem.id}
                  >
                    {/* Avatar - Both User and Assistant */}
                    <Avatar className="w-8 h-8">
                      <div className="rounded-full bg-gray-100 border p-1">
                        {conversationItem.role === "assistant" ? (
                          <svg
                            stroke="none"
                            fill="black"
                            strokeWidth="1.5"
                            viewBox="0 0 24 24"
                            aria-hidden="true"
                            height="20"
                            width="20"
                            xmlns="http://www.w3.org/2000/svg"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
                            />
                          </svg>
                        ) : (
                          <svg
                            stroke="none"
                            fill="black"
                            strokeWidth="0"
                            viewBox="0 0 16 16"
                            height="20"
                            width="20"
                            xmlns="http://www.w3.org/2000/svg"
                          >
                            <path d="M8 8a3 3 0 100-6 3 3 0 000 6zm2-3a2 2 0 11-4 0 2 2 0 014 0zm4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4zm-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10c-2.29 0-3.516.68-4.168 1.332-.678.678-.83 1.418-.832 1.664h10z" />
                          </svg>
                        )}
                      </div>
                    </Avatar>
  
                    {/* Message Content */}
                    <div className="flex-1">
                      <div className="font-semibold mb-1">
                        {conversationItem.role === "user" ? "You" : "AI"}
                      </div>
                      <div className="prose whitespace-pre-wrap break-words leading-relaxed">
                        {conversationItem.role === "user" && (
                          <div>
                            {conversationItem.formatted.text ?? conversationItem.formatted.transcript ??
                            (conversationItem.formatted.audio?.length ? "(awaiting transcript)" : "(item sent)")
                            }
                          </div>
                        )}
                        {conversationItem.role === "assistant" && (
                          <div>
                            {conversationItem.formatted.text ??
                               conversationItem.formatted.transcript ??
                              "(was interrupted)"}
                          </div>
                        )}
                        {conversationItem.formatted.file && (
                          <div className="mt-2">
                            <audio
                              src={conversationItem.formatted.file.url}
                              controls
                              className="w-full max-w-[300px]"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>
  
      <div className="visualization flex justify-center gap-8 p-4 border-t">
        <div className="visualization-entry client w-32">
          <canvas ref={clientCanvasRef} className="w-full h-16" />
        </div>
        <div className="visualization-entry server w-32">
          <canvas ref={serverCanvasRef} className="w-full h-16" />
        </div>
      </div>
  
      <div className="p-4 border-t mt-auto">
        <div className="flex flex-col gap-4">
          <button
            onClick={disconnectConversation}
            className="w-full bg-gray-100 hover:bg-gray-200 text-gray-800 font-semibold py-2 px-4 rounded"
          >
            Back to Chat
          </button>
        </div>
      </div>
    </div>
  );    
}












