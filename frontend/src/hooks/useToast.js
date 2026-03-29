import { useState, useCallback } from "react";

export function useToast() {
  const [toastMsg, setToastMsg] = useState(null);

  const toast = useCallback((message, type = "success") => {
    setToastMsg({ message, type });
    setTimeout(() => setToastMsg(null), 3500);
  }, []);

  const clearToast = useCallback(() => setToastMsg(null), []);

  return { toastMsg, toast, clearToast };
}
