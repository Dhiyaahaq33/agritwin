import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="flex flex-col items-center gap-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-green-400">🌱 AgriTwin</h1>
          <p className="text-sm text-gray-500 mt-1">AI Greenhouse Digital Twin</p>
        </div>
        <SignIn
          appearance={{
            elements: {
              rootBox:       "bg-gray-900 border border-gray-800 rounded-xl",
              card:          "bg-gray-900 shadow-none",
              headerTitle:   "text-gray-100",
              headerSubtitle:"text-gray-400",
              formFieldLabel:"text-gray-300",
              formFieldInput:"bg-gray-800 border-gray-700 text-gray-100 focus:border-green-500",
              footerActionLink:"text-green-400 hover:text-green-300",
              formButtonPrimary:"bg-green-600 hover:bg-green-500",
            },
          }}
        />
      </div>
    </main>
  );
}
