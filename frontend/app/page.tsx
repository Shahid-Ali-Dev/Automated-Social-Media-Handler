"use client";

import { useState, useEffect } from "react";

export default function Home() {
  const [baseText, setBaseText] = useState("");
  const [platform, setPlatform] = useState("General");
  const [isLoading, setIsLoading] = useState(false);
  
  const [history, setHistory] = useState<any[]>([]);
  const [isFetchingHistory, setIsFetchingHistory] = useState(true);
  
  // State to manage the confirmation modal
  const [postToDelete, setPostToDelete] = useState<number | null>(null);
  
  // State to manage the media upload loading state
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  // Toggle for AI vs Manual
  const [isManualMode, setIsManualMode] = useState(false);
  
  // Manual Creation States
  const [manualTitle, setManualTitle] = useState("");
  const [manualDesc, setManualDesc] = useState("");
  const [manualTags, setManualTags] = useState("");

  // Inline Editing States
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "", hashtags: "" });

  // Publishing State
  const [isPublishing, setIsPublishing] = useState<number | null>(null);

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setIsFetchingHistory(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/history`);
      if (response.ok) {
        const data = await response.json();
        setHistory(data.posts);
      }
    } catch (error) {
      console.error("Failed to fetch history:", error);
    } finally {
      setIsFetchingHistory(false);
    }
  };

  const handleManualSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    // Convert comma-separated string to array, remove whitespace
    const tagsArray = manualTags.split(",").map(tag => tag.trim()).filter(tag => tag !== "");

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          platform: platform, 
          title: manualTitle, 
          description: manualDesc, 
          hashtags: tagsArray 
        }),
      });

      if (response.ok) {
        setManualTitle(""); setManualDesc(""); setManualTags("");
        fetchHistory();
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  const startEditing = (post: any) => {
    setEditingId(post.id);
    setEditForm({
      title: post.enhanced_title,
      description: post.enhanced_description,
      hashtags: post.hashtags ? post.hashtags.join(", ") : ""
    });
  };

  const saveEdit = async (id: number) => {
    const tagsArray = editForm.hashtags.split(",").map(tag => tag.trim()).filter(tag => tag !== "");
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/posts/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: editForm.title,
          description: editForm.description,
          hashtags: tagsArray
        }),
      });

      if (response.ok) {
        setEditingId(null);
        fetchHistory();
      }
    } catch (error) {
      console.error(error);
    }
  };
const handlePublishToLinkedIn = async (postId: number) => {
    setIsPublishing(postId);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/publish/linkedin/${postId}`, {
        method: "POST",
      });
      
      const data = await response.json();
      
      if (response.ok) {
        alert("Success! Your post is live on LinkedIn.");
        fetchHistory(); 
      } else {
        alert(`Failed to post: ${data.detail}`);
      }
    } catch (error) {
      console.error("Publish error:", error);
      alert("Something went wrong connecting to the backend.");
    } finally {
      setIsPublishing(null);
    }
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

      if (response.ok) {
        setBaseText("");
        fetchHistory(); 
      } else {
        alert("Generation failed. Check the server logs.");
      }
    } catch (error) {
      console.error(error);
      alert("Something went wrong connecting to the backend.");
    } finally {
      setIsLoading(false);
    }
  };

  // ACTUAL delete function called ONLY when confirmed
  const executeDelete = async () => {
    if (postToDelete === null) return;
    
    const idToDelete = postToDelete;
    
    // 1. Close the modal immediately
    setPostToDelete(null);
    
    // 2. Optimistic UI update
    setHistory(history.filter((post) => post.id !== idToDelete));
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/history/${idToDelete}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        fetchHistory();
        alert("Failed to delete post.");
      }
    } catch (error) {
      console.error("Delete failed:", error);
      fetchHistory();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, postId: number) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploadingId(postId);

    const formData = new FormData();
    formData.append("post_id", postId.toString());
    
    // Append ALL selected files
    Array.from(files).forEach((file) => {
      formData.append("files", file); 
    });

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/media/upload`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) fetchHistory();
    } catch (error) {
      console.error("Upload error:", error);
    } finally {
      setUploadingId(null);
    }
  };

  const handleDeleteMedia = async (mediaId: number) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/media/${mediaId}`, {
        method: "DELETE",
      });
      if (response.ok) fetchHistory();
    } catch (error) {
      console.error("Failed to delete media:", error);
    }
  };
const handlePublishToFacebook = async (postId: number) => {
    setIsPublishing(postId);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/publish/facebook/${postId}`, { method: "POST" });
      if (res.ok) { alert("Live on Facebook!"); fetchHistory(); } 
      else { const err = await res.json(); alert(`FB Error: ${err.detail}`); }
    } finally { setIsPublishing(null); }
  };

  const handlePublishToInstagram = async (postId: number) => {
    setIsPublishing(postId);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/publish/instagram/${postId}`, { method: "POST" });
      if (res.ok) { alert("Live on Instagram!"); fetchHistory(); } 
      else { const err = await res.json(); alert(`IG Error: ${err.detail}`); }
    } finally { setIsPublishing(null); }
  };
  const handlePublishToX = async (postId: number) => {
    setIsPublishing(postId);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/publish/x/${postId}`, {
        method: "POST",
      });
      
      const data = await response.json();
      
      if (response.ok) {
        alert("Success! Your post is live on X.");
        fetchHistory(); // Refresh to show the updated 'Posted' status
      } else {
        alert(`Failed to post: ${data.detail}`);
      }
    } catch (error) {
      console.error("Publish error:", error);
      alert("Something went wrong connecting to the backend.");
    } finally {
      setIsPublishing(null);
    }
  };

  return (
    <main className="min-h-screen bg-gray-100 text-gray-900 p-8 font-sans relative">
      
      {/* --- CONFIRMATION MODAL OVERLAY --- */}
      {postToDelete !== null && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-2xl shadow-xl max-w-sm w-full border border-gray-100 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="text-xl font-bold mb-2 text-gray-900">Delete Post?</h3>
            <p className="text-gray-500 mb-6 text-sm">
              Are you sure you want to delete this generated post? This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button 
                onClick={() => setPostToDelete(null)}
                className="px-4 py-2 text-gray-600 font-semibold hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={executeDelete}
                className="px-4 py-2 bg-red-600 text-white font-semibold hover:bg-red-700 rounded-lg transition-colors shadow-sm shadow-red-200"
              >
                Yes, Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-extrabold tracking-tight mb-8">Social Auto Engine</h1>
        
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* LEFT COLUMN: THE GENERATOR */}
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-200">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold">Create Post</h2>
                
                {/* AI / Manual Toggle Switch */}
                <div className="flex items-center gap-2 bg-gray-100 p-1 rounded-lg">
                  <button 
                    onClick={() => setIsManualMode(false)}
                    className={`px-3 py-1 text-sm font-semibold rounded-md transition-all ${!isManualMode ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                  >
                    AI Assist
                  </button>
                  <button 
                    onClick={() => setIsManualMode(true)}
                    className={`px-3 py-1 text-sm font-semibold rounded-md transition-all ${isManualMode ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                  >
                    Manual
                  </button>
                </div>
              </div>

              {/* Platform Selector (Shared by both modes) */}
              <div className="mb-4">
                <label className="block text-sm font-semibold text-gray-700 mb-1">Target Platform</label>
                <select 
                  value={platform} 
                  onChange={(e) => setPlatform(e.target.value)}
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                >
                  <option value="General">General</option>
                  <option value="LinkedIn">LinkedIn</option>
                  <option value="Twitter/X">Twitter/X</option>
                  <option value="Instagram">Instagram</option>
                </select>
              </div>

              {!isManualMode ? (
                /* AI Enhancement Form */
                <form onSubmit={handleEnhance} className="space-y-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">Rough Draft</label>
                    <textarea 
                      value={baseText}
                      onChange={(e) => setBaseText(e.target.value)}
                      placeholder="Type your rough idea here..."
                      className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl h-32 focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                      required
                    />
                  </div>
                  <button type="submit" disabled={isLoading} className="w-full bg-blue-600 text-white py-3 rounded-xl font-bold hover:bg-blue-700 disabled:bg-blue-300 shadow-md transition-colors">
                    {isLoading ? "Generating..." : "Enhance & Save"}
                  </button>
                </form>
              ) : (
                /* Manual Entry Form */
                <form onSubmit={handleManualSave} className="space-y-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">Title</label>
                    <input type="text" value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} required className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" placeholder="Catchy Hook..." />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">Description</label>
                    <textarea value={manualDesc} onChange={(e) => setManualDesc(e.target.value)} required className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl h-32 focus:ring-2 focus:ring-blue-500 outline-none resize-none" placeholder="Write your post content..." />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">Hashtags (comma separated)</label>
                    <input type="text" value={manualTags} onChange={(e) => setManualTags(e.target.value)} className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" placeholder="tech, coding, update..." />
                  </div>
                  <button type="submit" disabled={isLoading} className="w-full bg-gray-900 text-white py-3 rounded-xl font-bold hover:bg-black shadow-md transition-colors">
                    {isLoading ? "Saving..." : "Save Post"}
                  </button>
                </form>
              )}
            </div>
          </div>

          {/* RIGHT COLUMN: THE HISTORY FEED */}
          <div className="lg:col-span-7">
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 h-[calc(100vh-8rem)] overflow-y-auto">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold">Your Generations</h2>
                <span className="text-sm font-medium text-gray-500 bg-gray-100 px-3 py-1 rounded-full">
                  {history.length} Saved
                </span>
              </div>

              {isFetchingHistory ? (
                <p className="text-gray-500 text-center py-10 animate-pulse">Loading database history...</p>
              ) : history.length === 0 ? (
                <p className="text-gray-500 text-center py-10 bg-gray-50 rounded-xl border border-dashed border-gray-300">
                  No posts yet. Generate your first one!
                </p>
              ) : (
                <div className="space-y-4">
                  {history.map((post) => (
                    <div key={post.id} className="group relative bg-gray-50 p-5 rounded-xl border border-gray-200 hover:border-blue-300 transition-colors">
                      
                      <div className="flex flex-col md:flex-row gap-5">
                        
                        {/* Media Gallery Section */}
                        <div className="w-full md:w-1/3 flex flex-col gap-3">
                          {/* Image Grid */}
                          {post.media_files && post.media_files.length > 0 ? (
                            <div className="grid grid-cols-2 gap-2">
                              {post.media_files.map((media: any) => (
                                <div key={media.id} className="relative group/media">
                                  <img 
                                    src={media.url} 
                                    className="w-full h-24 object-cover rounded-lg border border-gray-200"
                                    alt="Post attachment"
                                  />
                                  {/* Delete Individual Image Button */}
                                  <button 
                                    onClick={() => handleDeleteMedia(media.id)}
                                    className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover/media:opacity-100 transition-opacity shadow-sm hover:bg-red-600"
                                    title="Remove Image"
                                  >
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                                    </svg>
                                  </button>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="w-full h-24 bg-gray-100 rounded-lg flex items-center justify-center border border-dashed border-gray-300">
                              <span className="text-gray-400 text-xs">No Media</span>
                            </div>
                          )}
                          
                          {/* Multi-File Upload Input */}
                          <label className="cursor-pointer text-center text-xs font-semibold text-blue-600 bg-blue-50 py-2 rounded-lg hover:bg-blue-100 transition-colors">
                            {uploadingId === post.id ? "Uploading..." : "Add Images/Videos"}
                            <input 
                              type="file" 
                              multiple 
                              className="hidden" 
                              accept="image/*,video/*"
                              onChange={(e) => handleFileUpload(e, post.id)}
                              disabled={uploadingId === post.id}
                            />
                          </label>
                        </div>

                        {/* Text Content Section */}
                        <div className="w-full md:w-2/3 relative flex flex-col h-full">
                          
                          {/* Top Right Actions (Edit & Delete) */}
                          <div className="absolute -top-2 -right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                            {editingId !== post.id && (
                              <button onClick={() => startEditing(post)} className="bg-white p-2 text-gray-500 hover:text-blue-500 rounded-full shadow border border-gray-100" title="Edit Content">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                  <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                                </svg>
                              </button>
                            )}
                            <button onClick={() => setPostToDelete(post.id)} className="bg-white p-2 text-gray-500 hover:text-red-500 rounded-full shadow border border-gray-100" title="Delete Post">
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>

                          <div className="flex items-center gap-2 mb-2">
                            <span className="bg-black text-white text-xs font-bold px-2 py-1 rounded-md">{post.platform}</span>
                            
                            {/* Status Badge */}
                            <span className={`text-xs font-bold px-2 py-1 rounded-md ${post.status === 'Posted' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                              {post.status}
                            </span>
                          </div>

                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs text-gray-400 font-medium">
                              {new Date(post.created_at).toLocaleDateString()}
                            </span>
                          </div>

                          {editingId === post.id ? (
                            /* Inline Edit Mode */
                            <div className="space-y-3 mt-2">
                              <input 
                                type="text" 
                                value={editForm.title} 
                                onChange={(e) => setEditForm({...editForm, title: e.target.value})}
                                className="w-full p-2 border border-blue-300 rounded focus:ring-2 focus:ring-blue-500 outline-none font-bold text-lg bg-white" 
                              />
                              <textarea 
                                value={editForm.description} 
                                onChange={(e) => setEditForm({...editForm, description: e.target.value})}
                                className="w-full p-2 border border-blue-300 rounded h-32 focus:ring-2 focus:ring-blue-500 outline-none text-sm resize-none bg-white" 
                              />
                              <input 
                                type="text" 
                                value={editForm.hashtags} 
                                onChange={(e) => setEditForm({...editForm, hashtags: e.target.value})}
                                className="w-full p-2 border border-blue-300 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm bg-white"
                                placeholder="Comma separated hashtags" 
                              />
                              <div className="flex gap-2 pt-1">
                                <button onClick={() => saveEdit(post.id)} className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm font-bold hover:bg-blue-700">Save</button>
                                <button onClick={() => setEditingId(null)} className="bg-gray-200 text-gray-700 px-4 py-1.5 rounded text-sm font-bold hover:bg-gray-300">Cancel</button>
                              </div>
                            </div>
                          ) : (
                            /* Normal Display Mode */
                            <>
                              <h3 className="font-bold text-lg mb-1">{post.enhanced_title}</h3>
                              <p className="text-gray-700 text-sm whitespace-pre-wrap mb-3">{post.enhanced_description}</p>
                              
                              <div className="flex flex-wrap gap-2 mt-2">
                                {post.hashtags && post.hashtags.map((tag: string, index: number) => (
                                  <span key={index} className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-1 rounded-md">
                                    #{tag}
                                  </span>
                                ))}
                              </div>
                            </>
                          )}

                          {/* Publish Buttons Grid */}
                          {!editingId && (
                            <div className="mt-auto pt-4 border-t border-gray-100 grid grid-cols-2 gap-2">
                              <button onClick={() => handlePublishToLinkedIn(post.id)} disabled={isPublishing === post.id} className="bg-[#0A66C2] text-white py-2 rounded-lg font-bold hover:bg-[#004182] disabled:opacity-50 text-xs">
                                LinkedIn
                              </button>
                              
                              <button onClick={() => handlePublishToFacebook(post.id)} disabled={isPublishing === post.id} className="bg-[#1877F2] text-white py-2 rounded-lg font-bold hover:bg-[#0d5ebd] disabled:opacity-50 text-xs">
                                Facebook
                              </button>

                              <button onClick={() => handlePublishToInstagram(post.id)} disabled={isPublishing === post.id} className="bg-gradient-to-tr from-[#F58529] via-[#DD2A7B] to-[#8134AF] text-white py-2 rounded-lg font-bold hover:opacity-90 disabled:opacity-50 text-xs">
                                Instagram
                              </button>

                              <button onClick={() => alert("Waiting for billing!")} className="bg-gray-200 text-gray-500 py-2 rounded-lg font-bold cursor-not-allowed text-xs">
                                X (Needs API Credits)
                              </button>
                            </div>
                          )}
                        </div>

                      </div>
                    </div>
                    
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}