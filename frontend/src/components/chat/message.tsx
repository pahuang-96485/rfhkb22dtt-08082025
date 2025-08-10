"use client";

import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Avatar } from "../avatar";
import { Ring } from "@uiball/loaders";
import { cn } from "@/utils/utils";

export default function Bubble({
  message,
  loading = false,
  isStreaming = false,
}: {
  message: { id: string; role: string; content: string };
  loading?: boolean;
  isStreaming?: boolean;
}) {
  const [displayedContent, setDisplayedContent] = useState(message.content);

  useEffect(() => {
    if (isStreaming) {
      setDisplayedContent(message.content);
    }
  }, [message.content, isStreaming]);

  // Helper to handle tool-based markdown replacement
  // Allow `content` to be undefined and default to an empty string
  const formatMessage = (content?: string) => {
    const text = content ?? ""
    return text
      .replaceAll(`<|loading_tools|>`, `\n\n**Loading tools...**`)
      .replaceAll(`<|tool_error|>`, `\n\n⚠️ **Tool Error**`)
      .replaceAll(/\<\|tool_called[\s\S]*\$\$/g, (match) => {
        const parts = match.split("$$");
        return `\n\n**${parts[1]}** ${
          parts[2] === "false" ? "🛠️" : "⚡"
        }`;
      })
      .replace(/^(\d+)\.\s/gm, "$1\\. ") ////added
      .replace(/\n/g, "  \n"); 
  };

  return (
    <div
      key={message.id}
      className="flex gap-3 my-4 text-gray-600 text-sm flex-1"
    >
      {/* User Avatar */}
      {message.role === "user" && (
        <Avatar className="w-8 h-8">
          <div className="rounded-full bg-gray-100 border p-1">
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
          </div>
        </Avatar>
      )}

      {/* Assistant Avatar */}
      {message.role === "assistant" && (
        <Avatar className="w-8 h-8">
          <div
            className={cn(
              "rounded-full bg-gray-100 border p-1",
              (loading || isStreaming) && "animate-pulse"
            )}
          >
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
          </div>
        </Avatar>
      )}

      {/* Message Content */}
      <div className="leading-relaxed">
        <span className="block font-bold text-gray-700 mb-2">
          {message.role === "user" ? "You" : "AI"}
        </span>

        {/* Markdown Handling */}
        {!loading && (
          <div className="prose whitespace-pre-wrap break-words leading-relaxed">
            <ReactMarkdown>
              {formatMessage(displayedContent)}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block w-2 h-4 ml-1 bg-gray-400 animate-pulse"></span>
            )}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="my-2 flex items-center gap-2">
            <Ring size={20} color="#1a1a1a" />
            <span>Loading...</span>
          </div>
        )}
      </div>
    </div>
  );
}




