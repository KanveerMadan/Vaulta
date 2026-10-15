import { useNavigate } from "react-router-dom";
import ReviewFlow from "../components/ReviewFlow";

export default function Review() {
  const navigate = useNavigate();
  return (
    <div className="max-w-xl mx-auto space-y-4">
      <h1 className="font-display text-2xl text-ink-900">Review</h1>
      <ReviewFlow onDone={() => navigate("/")} doneLabel="Back to home" />
    </div>
  );
}
