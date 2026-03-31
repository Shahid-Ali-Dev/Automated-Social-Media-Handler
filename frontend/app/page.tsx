"use client";

import { useState, useEffect } from "react";

// --- OFFICIAL BRAND ICONS ---
const Icons = {
  General: () => (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09l2.846.813-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
    </svg>
  ),
  Facebook: () => (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M22 12c0-5.523-4.477-10-10-10S2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.878v-6.987h-2.54V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.988C18.343 21.128 22 16.991 22 12z" /></svg>
  ),
  Instagram: () => (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" d="M12.315 2c2.43 0 2.784.013 3.808.06 1.064.049 1.791.218 2.427.465a4.902 4.902 0 011.772 1.153 4.902 4.902 0 011.153 1.772c.247.636.416 1.363.465 2.427.048 1.067.06 1.407.06 4.123v.08c0 2.643-.012 2.987-.06 4.043-.049 1.064-.218 1.791-.465 2.427a4.902 4.902 0 01-1.153 1.772 4.902 4.902 0 01-1.772 1.153c-.636.247-1.363.416-2.427.465-1.067.048-1.407.06-4.123.06h-.08c-2.643 0-2.987-.012-4.043-.06-1.064-.049-1.791-.218-2.427-.465a4.902 4.902 0 01-1.772-1.153 4.902 4.902 0 01-1.153-1.772c-.247-.636-.416-1.363-.465-2.427-.047-1.024-.06-1.379-.06-3.808v-.63c0-2.43.013-2.784.06-3.808.049-1.064.218-1.791.465-2.427a4.902 4.902 0 011.153-1.772A4.902 4.902 0 015.45 2.525c.636-.247 1.363-.416 2.427-.465C8.901 2.013 9.256 2 11.685 2h.63zm-.081 1.802h-.468c-2.456 0-2.784.011-3.807.058-.975.045-1.504.207-1.857.344-.467.182-.8.398-1.15.748-.35.35-.566.683-.748 1.15-.137.353-.3.882-.344 1.857-.047 1.023-.058 1.351-.058 3.807v.468c0 2.456.011 2.784.058 3.807.045.975.207 1.504.344 1.857.182.466.399.8.748 1.15.35.35.683.566 1.15.748.353.137.882.3 1.857.344 1.054.048 1.37.058 4.041.058h.08c2.597 0 2.917-.01 3.96-.058.976-.045 1.505-.207 1.858-.344.466-.182.8-.398 1.15-.748.35-.35.566-.683.748-1.15.137-.353.3-.882.344-1.857.048-1.055.058-1.37.058-4.041v-.08c0-2.597-.01-2.917-.058-3.96-.045-.976-.207-1.505-.344-1.858a3.097 3.097 0 00-.748-1.15 3.098 3.098 0 00-1.15-.748c-.353-.137-.882-.3-1.857-.344-1.023-.047-1.351-.058-3.807-.058zM12 6.865a5.135 5.135 0 110 10.27 5.135 5.135 0 010-10.27zm0 1.802a3.333 3.333 0 100 6.666 3.333 3.333 0 000-6.666zm5.338-3.205a1.2 1.2 0 110 2.4 1.2 1.2 0 010-2.4z" clipRule="evenodd" /></svg>
  ),
  LinkedIn: () => (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" clipRule="evenodd" /></svg>
  ),
  YouTube: () => (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
  ),
  X: () => (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 22.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.008 5.96H5.078z" /></svg>
  ),
  Threads: () => (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12.012 2C6.48 2 2 6.48 2 12.012c0 5.531 4.48 10.012 10.012 10.012 5.531 0 10.012-4.48 10.012-10.012C22.024 6.48 17.543 2 12.012 2Zm3.472 14.545c-1.12.946-2.585 1.135-4.104.912-1.353-.2-2.502-.876-3.238-1.996-1.196-1.821-1.025-4.526.438-6.191 1.09-1.238 2.656-1.761 4.298-1.558 1.954.24 3.447 1.487 3.93 3.327.34 1.306.12 2.673-.62 3.824-.46.717-1.056 1.155-1.782 1.34-1.09.28-2.148-.206-2.508-1.258-.297-.866.074-1.874.622-2.597.43-.568.995-1.025 1.576-1.428.188-.13.38-.255.577-.37.31-.183.504-.543.433-.902-.09-.446-.494-.741-.954-.741-.663 0-1.29.35-1.666.92-.61.92-.816 2.072-.651 3.16.155 1.025.753 1.952 1.637 2.39 1.096.543 2.454.346 3.366-.453.642-.562.981-1.328 1.05-2.176.082-1.018-.216-1.996-.79-2.8-.846-1.185-2.197-1.802-3.65-1.685-1.574.126-2.99 1.022-3.702 2.433-.706 1.396-.706 3.033 0 4.43.712 1.411 2.128 2.306 3.702 2.433 1.085.087 2.164-.202 3.064-.787.524-.342.712-1.042.42-1.602-.29-.56-1.002-.74-1.565-.398Z"/></svg>
  ),
};

const PLATFORMS = [
  { id: 'General', icon: <Icons.General />, color: 'text-indigo-600', bg: 'hover:bg-indigo-50 border-indigo-200' },
  { id: 'LinkedIn', icon: <Icons.LinkedIn />, color: 'text-[#0A66C2]', bg: 'hover:bg-blue-50 border-blue-200' },
  { id: 'Facebook', icon: <Icons.Facebook />, color: 'text-[#1877F2]', bg: 'hover:bg-blue-50 border-blue-200' },
  { id: 'Instagram', icon: <Icons.Instagram />, color: 'text-[#E4405F]', bg: 'hover:bg-pink-50 border-pink-200' },
  { id: 'Twitter/X', icon: <Icons.X />, color: 'text-black', bg: 'hover:bg-gray-100 border-gray-300' },
  { id: 'YouTube', icon: <Icons.YouTube />, color: 'text-[#FF0000]', bg: 'hover:bg-red-50 border-red-200' },
  { id: 'Threads', icon: <Icons.Threads />, color: 'text-black', bg: 'hover:bg-gray-100 border-gray-300' },
];

// Helper to format dates cleanly
const formatDate = (dateString: string) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date);
};

// Helper to check if a URL is a video
const isVideoMedia = (url: string) => /\.(mp4|mov|webm|avi|mkv)$/i.test(url) || url.includes('/video/upload/');

export default function Home() {
  const [baseText, setBaseText] = useState("");
  const [platform, setPlatform] = useState("General");
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [isFetchingHistory, setIsFetchingHistory] = useState(true);
  const [postToDelete, setPostToDelete] = useState<number | null>(null);
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const [isManualMode, setIsManualMode] = useState(false);
  const [manualTitle, setManualTitle] = useState("");
  const [manualDesc, setManualDesc] = useState("");
  const [manualTags, setManualTags] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "", hashtags: "" });
  const [isPublishing, setIsPublishing] = useState<number | null>(null);
  const [publishModalOpen, setPublishModalOpen] = useState<number | null>(null);
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [adminPassword, setAdminPassword] = useState("");
  const [logsModalOpen, setLogsModalOpen] = useState<any[] | null>(null);

  useEffect(() => { fetchHistory(); }, []);

  const fetchHistory = async () => {
    setIsFetchingHistory(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/history`);
      if (response.ok) {
        const data = await response.json();
        setHistory(data.posts);
      }
    } catch (error) { console.error("Failed to fetch history:", error); } 
    finally { setIsFetchingHistory(false); }
  };

  const handleEnhance = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/enhance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_text: baseText, platform: platform }),
      });
      if (response.ok) { setBaseText(""); fetchHistory(); } 
      else { alert("Generation failed."); }
    } catch (error) { alert("Something went wrong."); } 
    finally { setIsLoading(false); }
  };

  const handleManualSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    const tagsArray = manualTags.split(",").map(tag => tag.trim()).filter(tag => tag !== "");
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: platform, title: manualTitle, description: manualDesc, hashtags: tagsArray }),
      });
      if (response.ok) { setManualTitle(""); setManualDesc(""); setManualTags(""); fetchHistory(); }
    } catch (error) { console.error(error); } 
    finally { setIsLoading(false); }
  };

  const handleUnifiedPublish = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!publishModalOpen || selectedPlatforms.length === 0) return;
    
    setIsPublishing(publishModalOpen);
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/publish/unified/${publishModalOpen}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platforms: selectedPlatforms,
          admin_password: adminPassword
        })
      });
      
      const data = await response.json();
      
      if (response.ok) {
        // CLOSE publish modal, RESET form, REFRESH history
        setPublishModalOpen(null);
        setAdminPassword("");
        setSelectedPlatforms([]);
        fetchHistory(); 
        
        // OPEN the logs modal instantly with the fresh results!
        setLogsModalOpen(data.logs); 
      } else {
        // Show server-level errors (like wrong password) beautifully
        setLogsModalOpen([{ platform: "System", status: "Failed", error_message: data.detail }]);
      }
    } catch (error) {
      console.error(error);
      setLogsModalOpen([{ platform: "Network", status: "Failed", error_message: "Failed to connect to the backend server." }]);
    } finally {
      setIsPublishing(null);
    }
  };

  const fetchLogsForPost = async (postId: number) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/publish/logs/${postId}`);
      if (response.ok) {
        const data = await response.json();
        setLogsModalOpen(data.logs);
      } else { alert("Failed to fetch logs."); }
    } catch (error) { console.error("Failed to fetch logs:", error); }
  };

  const togglePlatform = (platId: string) => {
    setSelectedPlatforms(prev => prev.includes(platId) ? prev.filter(p => p !== platId) : [...prev, platId]);
  };

  const startEditing = (post: any) => {
    setEditingId(post.id);
    setEditForm({ title: post.enhanced_title, description: post.enhanced_description, hashtags: post.hashtags ? post.hashtags.join(", ") : "" });
  };

  const saveEdit = async (id: number) => {
    const tagsArray = editForm.hashtags.split(",").map(tag => tag.trim()).filter(tag => tag !== "");
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/posts/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: editForm.title, description: editForm.description, hashtags: tagsArray }),
      });
      if (response.ok) { setEditingId(null); fetchHistory(); }
    } catch (error) { console.error(error); }
  };

  const executeDelete = async () => {
    if (postToDelete === null) return;
    const idToDelete = postToDelete;
    setPostToDelete(null);
    setHistory(history.filter((post) => post.id !== idToDelete));
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/history/${idToDelete}`, { method: "DELETE" });
      if (!response.ok) fetchHistory();
    } catch (error) { fetchHistory(); }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, postId: number) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploadingId(postId);
    const formData = new FormData();
    formData.append("post_id", postId.toString());
    Array.from(files).forEach((file) => { formData.append("files", file); });

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/media/upload`, { method: "POST", body: formData });
      if (response.ok) fetchHistory();
    } catch (error) { console.error("Upload error:", error); } 
    finally { setUploadingId(null); }
  };

  const handleDeleteMedia = async (mediaId: number) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/media/${mediaId}`, { method: "DELETE" });
      if (response.ok) fetchHistory();
    } catch (error) { console.error(error); }
  };

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 p-8 font-sans relative selection:bg-indigo-200">
      
      {/* --- CONFIRMATION MODAL OVERLAY --- */}
      {postToDelete !== null && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-2xl shadow-xl max-w-sm w-full border border-slate-100">
            <h3 className="text-xl font-bold mb-2 text-slate-900">Delete Post?</h3>
            <p className="text-slate-500 mb-6 text-sm">Are you sure you want to delete this generated post? This action cannot be undone.</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setPostToDelete(null)} className="px-4 py-2 text-slate-600 font-semibold hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button onClick={executeDelete} className="px-4 py-2 bg-red-600 text-white font-semibold hover:bg-red-700 rounded-lg transition-colors shadow-sm shadow-red-200">Yes, Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* --- LOGS MODAL OVERLAY --- */}
      {logsModalOpen !== null && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white p-6 rounded-2xl shadow-xl max-w-lg w-full border border-slate-100 flex flex-col max-h-[85vh]">
            <h3 className="text-2xl font-bold mb-4 text-slate-900">Publish Results</h3>
            
            <div className="space-y-4 mb-6 overflow-y-auto custom-scrollbar pr-2">
              {logsModalOpen.length === 0 ? (
                <p className="text-slate-500 text-sm text-center py-4 border-2 border-dashed rounded-xl">No logs found.</p>
              ) : (
                logsModalOpen.map((log, idx) => (
                  <div key={idx} className={`p-4 rounded-xl border ${log.status === 'Success' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                    
                    {/* Header: Platform, Badge, and Time */}
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-extrabold text-slate-800">{log.platform}</span>
                        <span className={`text-xs px-2.5 py-1 rounded-md font-bold uppercase tracking-wide ${
                          log.status === 'Success' ? 'bg-green-200 text-green-800' : 
                          log.status === 'Skipped' ? 'bg-amber-200 text-amber-800' : 
                          'bg-red-200 text-red-800'
                        }`}>
                          {log.status}
                        </span>
                      </div>
                      <span className="text-xs text-slate-400 font-bold bg-white px-2 py-1 rounded-md shadow-sm border border-slate-100">
                        {log.published_at ? formatDate(log.published_at) : "Just now"}
                      </span>
                    </div>

                    {/* Error Message Box (Handles both DB logs and instant API response keys) */}
                    {(log.error_message || log.error) && (
                      <div className="mt-3 bg-white border border-red-100 rounded-lg p-3 shadow-inner overflow-hidden">
                        <p className="text-xs text-red-600 font-mono break-words whitespace-pre-wrap leading-relaxed">
                          {log.error_message || log.error}
                        </p>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
            
            <button 
              onClick={() => setLogsModalOpen(null)} 
              className="w-full py-3 bg-slate-100 text-slate-700 font-bold hover:bg-slate-200 rounded-xl transition-colors mt-auto"
            >
              Close Report
            </button>
          </div>
        </div>
      )}

      {/* --- PUBLISH MODAL OVERLAY --- */}
      {publishModalOpen && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-2xl w-full max-w-md shadow-2xl border border-slate-100">
            <h2 className="text-2xl font-bold mb-4">Publish Campaign</h2>
            
            <form onSubmit={handleUnifiedPublish} className="space-y-6">
              <div>
                <div className="flex justify-between items-end mb-3">
                  <label className="block text-sm font-bold text-slate-700">Select Networks</label>
                  <button type="button" onClick={() => setSelectedPlatforms(['LinkedIn', 'Facebook', 'Instagram', 'Twitter/X', 'YouTube', 'Threads'])} className="text-xs text-indigo-600 font-bold hover:underline">Select All</button>
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                  {PLATFORMS.filter(p => p.id !== 'General').map(plat => {
                    const isSelected = selectedPlatforms.includes(plat.id);
                    return (
                      <button
                        key={plat.id}
                        type="button"
                        onClick={() => togglePlatform(plat.id)}
                        className={`flex items-center gap-2 p-3 rounded-xl border-2 transition-all text-left ${isSelected ? `border-indigo-600 bg-indigo-50 ${plat.color}` : 'border-slate-200 hover:border-slate-300 text-slate-500'}`}
                      >
                        {plat.icon}
                        <span className={`text-sm font-semibold ${isSelected ? 'text-slate-900' : ''}`}>{plat.id}</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold mb-2 text-slate-700">Admin Password</label>
                <input 
                  type="password" 
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  className="w-full p-3 border border-slate-300 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow"
                  placeholder="Enter secret to confirm..."
                  required
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setPublishModalOpen(null)} className="flex-1 py-3 bg-slate-100 text-slate-700 rounded-xl font-bold hover:bg-slate-200 transition-colors">Cancel</button>
                <button type="submit" disabled={isPublishing !== null} className="flex-1 py-3 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-md shadow-indigo-200">
                  {isPublishing ? "Pushing Live..." : "Launch Post"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --- MAIN DASHBOARD LAYOUT --- */}
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-extrabold tracking-tight mb-8 text-slate-900">Social Auto Engine</h1>
        
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* LEFT COLUMN: THE GENERATOR */}
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold">New Post</h2>
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
                  <button onClick={() => setIsManualMode(false)} className={`px-4 py-1.5 text-sm font-bold rounded-md transition-all ${!isManualMode ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}>AI Assist</button>
                  <button onClick={() => setIsManualMode(true)} className={`px-4 py-1.5 text-sm font-bold rounded-md transition-all ${isManualMode ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}>Manual</button>
                </div>
              </div>

              {!isManualMode && (
                <div className="mb-6">
                  <label className="block text-sm font-bold text-slate-700 mb-2">Target Network Focus</label>
                  <div className="grid grid-cols-5 gap-2">
                    {PLATFORMS.map(plat => (
                      <button
                        key={plat.id}
                        onClick={() => setPlatform(plat.id)}
                        title={plat.id}
                        className={`flex justify-center p-3 rounded-xl border transition-all ${platform === plat.id ? `border-indigo-600 bg-indigo-50 ${plat.color} ring-1 ring-indigo-600` : `border-slate-200 bg-white text-slate-400 ${plat.bg} hover:text-slate-600`}`}
                      >
                        {plat.icon}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {!isManualMode ? (
                <form onSubmit={handleEnhance} className="space-y-5">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Draft Idea</label>
                    <textarea value={baseText} onChange={(e) => setBaseText(e.target.value)} placeholder="Type your rough idea here..." className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl h-36 focus:ring-2 focus:ring-indigo-500 outline-none resize-none transition-all" required />
                  </div>
                  <button type="submit" disabled={isLoading} className="w-full bg-indigo-600 text-white py-3.5 rounded-xl font-bold hover:bg-indigo-700 disabled:bg-indigo-300 shadow-md shadow-indigo-200 transition-all">
                    {isLoading ? "Generating Magic..." : "Enhance & Save to Drafts"}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleManualSave} className="space-y-4">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1">Title</label>
                    <input type="text" value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} required className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none transition-all" placeholder="Catchy Hook..." />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1">Description</label>
                    <textarea value={manualDesc} onChange={(e) => setManualDesc(e.target.value)} required className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl h-32 focus:ring-2 focus:ring-indigo-500 outline-none resize-none transition-all" placeholder="Write your post content..." />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1">Hashtags</label>
                    <input type="text" value={manualTags} onChange={(e) => setManualTags(e.target.value)} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none transition-all" placeholder="tech, coding, update..." />
                  </div>
                  <button type="submit" disabled={isLoading} className="w-full bg-slate-900 text-white py-3.5 rounded-xl font-bold hover:bg-slate-800 shadow-md transition-all">
                    {isLoading ? "Saving..." : "Save Manual Draft"}
                  </button>
                </form>
              )}
            </div>
          </div>

          {/* RIGHT COLUMN: THE HISTORY FEED */}
          <div className="lg:col-span-7">
            {/* Changed p-6 to px-6 pb-6 to remove top padding from the container */}
            <div className="bg-white px-6 pb-6 rounded-2xl shadow-sm border border-slate-200 h-[calc(100vh-8rem)] overflow-y-auto custom-scrollbar">
              
              {/* Added pt-6 here so the sticky header provides the top padding and covers the gap, bumped z-index to 20 */}
              <div className="flex justify-between items-center mb-6 sticky top-0 bg-white z-20 pt-6 pb-4 border-b border-slate-100">
                <h2 className="text-2xl font-bold">Content Library</h2>
                <span className="text-sm font-bold text-indigo-700 bg-indigo-50 px-3 py-1 rounded-full border border-indigo-100">
                  {history.length} Saved
                </span>
              </div>

              {isFetchingHistory ? (
                <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div></div>
              ) : history.length === 0 ? (
                <div className="text-center py-20 bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                  <span className="text-slate-400 font-medium">No posts yet. Generate your first one!</span>
                </div>
              ) : (
                <div className="space-y-6">
                  {history.map((post) => {
                    const platTheme = PLATFORMS.find(p => p.id === post.platform);
                    
                    return (
                    <div key={post.id} className="group relative bg-white p-6 rounded-2xl border border-slate-200 hover:border-indigo-300 hover:shadow-md transition-all">
                      <div className="flex flex-col md:flex-row gap-6">
                        
                        {/* Media Gallery Section */}
                        <div className="w-full md:w-1/3 flex flex-col gap-3">
                          {post.media_files && post.media_files.length > 0 ? (
                            <div className="grid grid-cols-2 gap-2">
                              {post.media_files.map((media: any) => (
                                <div key={media.id} className="relative group/media overflow-hidden rounded-xl border border-slate-200 bg-black">
                                  <img 
                                    src={media.url.replace(/\.(mp4|mov|webm)$/i, ".jpg")} 
                                    className="w-full h-24 object-cover hover:opacity-80 transition-opacity"
                                    alt="Post attachment"
                                  />
                                  
                                  {/* --- NEW: VIDEO PLAY BUTTON OVERLAY --- */}
                                  {isVideoMedia(media.url) && (
                                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                      <div className="bg-black/50 p-1.5 rounded-full backdrop-blur-sm shadow-sm">
                                        <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                                          <path d="M8 5v14l11-7z" />
                                        </svg>
                                      </div>
                                    </div>
                                  )}

                                  <button onClick={() => handleDeleteMedia(media.id)} className="absolute top-1 right-1 bg-red-500/90 backdrop-blur text-white rounded-full p-1.5 opacity-0 group-hover/media:opacity-100 transition-opacity hover:bg-red-600">
                                    <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
                                  </button>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="w-full h-24 bg-slate-50 rounded-xl flex items-center justify-center border-2 border-dashed border-slate-200">
                              <span className="text-slate-400 text-xs font-semibold">No Media Attached</span>
                            </div>
                          )}
                          
                          <label className="cursor-pointer text-center text-xs font-bold text-indigo-600 bg-indigo-50 py-2.5 rounded-xl hover:bg-indigo-100 transition-colors border border-indigo-100">
                            {uploadingId === post.id ? "Uploading..." : "+ Add Media"}
                            <input type="file" multiple className="hidden" accept="image/*,video/*" onChange={(e) => handleFileUpload(e, post.id)} disabled={uploadingId === post.id}/>
                          </label>
                        </div>

                        {/* Text Content Section */}
                        <div className="w-full md:w-2/3 relative flex flex-col h-full">
                          
                          <div className="absolute -top-2 -right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                            {!editingId && (
                              <button onClick={() => startEditing(post)} className="bg-white p-2 text-slate-400 hover:text-indigo-600 rounded-full shadow-sm border border-slate-100 transition-colors" title="Edit Content">
                                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" /></svg>
                              </button>
                            )}
                            <button onClick={() => setPostToDelete(post.id)} className="bg-white p-2 text-slate-400 hover:text-red-600 rounded-full shadow-sm border border-slate-100 transition-colors" title="Delete Post">
                              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                          </div>

                          <div className="flex items-center gap-3 mb-3">
                            <span className={`flex items-center gap-1.5 ${platTheme?.color} bg-slate-50 text-xs font-extrabold px-2.5 py-1 rounded-lg border border-slate-200`}>
                                {platTheme?.icon} {post.platform}
                            </span>
                            
                            <span className={`text-xs font-bold px-2.5 py-1 rounded-lg border ${post.status === 'Published' || post.status === 'Posted' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                              {post.status === 'Posted' ? 'Published' : post.status}
                            </span>

                            {/* --- MOVED DATE DISPLAY --- */}
                            {post.created_at && (
                              <span className="text-xs font-semibold text-slate-400" title="Created On">
                                • {formatDate(post.created_at)}
                              </span>
                            )}
                          </div>

                          {editingId === post.id ? (
                            <div className="space-y-3 mt-1 bg-slate-50 p-4 rounded-xl border border-slate-200">
                              <input type="text" value={editForm.title} onChange={(e) => setEditForm({...editForm, title: e.target.value})} className="w-full p-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none font-bold bg-white text-slate-900" />
                              <textarea value={editForm.description} onChange={(e) => setEditForm({...editForm, description: e.target.value})} className="w-full p-2 border border-slate-300 rounded-lg h-32 focus:ring-2 focus:ring-indigo-500 outline-none text-sm resize-none bg-white text-slate-700" />
                              <input type="text" value={editForm.hashtags} onChange={(e) => setEditForm({...editForm, hashtags: e.target.value})} className="w-full p-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none text-sm bg-white text-slate-700" placeholder="Comma separated hashtags" />
                              <div className="flex gap-2 pt-2">
                                <button onClick={() => saveEdit(post.id)} className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-indigo-700">Save Changes</button>
                                <button onClick={() => setEditingId(null)} className="bg-slate-200 text-slate-700 px-4 py-2 rounded-lg text-sm font-bold hover:bg-slate-300">Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <h3 className="font-extrabold text-xl mb-1 text-slate-900 leading-tight">{post.enhanced_title}</h3>
                              <p className="text-slate-600 text-sm whitespace-pre-wrap mb-4 leading-relaxed">{post.enhanced_description}</p>
                              
                              <div className="flex flex-wrap gap-1.5 mt-auto mb-4">
                                {post.hashtags && post.hashtags.map((tag: string, index: number) => (
                                  <span key={index} className="text-xs font-bold text-slate-600 bg-slate-100 px-2 py-1 rounded-md border border-slate-200">
                                    #{tag}
                                  </span>
                                ))}
                              </div>
                            </>
                          )}

                          {!editingId && (
                            <div className="mt-auto pt-4 border-t border-slate-100 flex gap-3">
                              <button onClick={() => setPublishModalOpen(post.id)} className="flex-1 bg-slate-900 text-white py-2.5 rounded-xl font-bold hover:bg-slate-800 transition-colors shadow-sm text-sm">
                                Publish Campaign...
                              </button>
                              
                              {(post.status === 'Published' || post.status === 'Posted') && (
                                <button onClick={() => fetchLogsForPost(post.id)} className="flex-1 bg-white text-slate-700 border-2 border-slate-200 py-2.5 rounded-xl font-bold hover:bg-slate-50 transition-colors text-sm">
                                  View Logs
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )})}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}