import { NextRequest, NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";

export async function POST(req: NextRequest) {
  if (!process.env.GEMINI_API_KEY)
    return NextResponse.json({ error: "GEMINI_API_KEY not configured" }, { status: 500 });
  const genai = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
  const model = genai.getGenerativeModel({ model: "gemini-2.0-flash" });
  try {
    const { prompt, zone_id } = await req.json();
    if (!prompt) return NextResponse.json({ error: "prompt required" }, { status: 400 });
    const context = zone_id ? `[Greenhouse Zone: ${zone_id}] ` : "";
    const result = await model.generateContent(
      `${context}Kamu adalah AI Agronomist untuk greenhouse. Jawab singkat dan praktis dalam bahasa Indonesia.\n\nPertanyaan: ${prompt}`
    );
    return NextResponse.json({ answer: result.response.text() });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
