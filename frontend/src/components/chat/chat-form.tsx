"use client";

import { Textarea } from "@/components/textarea";
import { useEffect, useRef, useState } from "react";
import { Ring } from "@uiball/loaders";
import { MicIcon } from "../icons/mic-icon";
import { Button } from "../button";

interface SendFormProps {
  input: string;
  handleSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  isLoading: boolean;
  handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onMicClick: () => void;
}

export default function SendForm({
  input,
  handleSubmit,
  isLoading,
  handleInputChange,
  onMicClick,
}: SendFormProps) {
  const [textareaHeight, setTextareaHeight] = useState("h-10");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (input.trim()) {
        handleSubmit(event as unknown as React.FormEvent<HTMLFormElement>);
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center justify-center w-full space-x-2">
      <div className="relative w-full max-w-xs">
        <MicIcon
          onClick={onMicClick}
          className="absolute right-2 h-4 w-4 top-1/2 -translate-y-2 text-gray-500 hover:text-blue-500 cursor-pointer"
        />

        <Textarea
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          className={`pr-8 resize-none mendable-textarea min-h-[20px] ${textareaHeight}`}
          placeholder="Type a message..."
          ref={textareaRef}
        />
      </div>

      <Button className="h-10" type="submit" disabled={isLoading}>
        {isLoading ? (
          <div className="flex gap-2 items-center">
            <Ring size={12} color="#1a1a1a" /> Loading...
          </div>
        ) : (
          "Send"
        )}
      </Button>
    </form>
  );
}



