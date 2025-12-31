// static/app.js

// 1. Import Firebase SDKs
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { 
    getAuth, 
    GoogleAuthProvider, 
    signInWithPopup, 
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    signOut, 
    onAuthStateChanged 
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// 2. CONFIGURATION
const firebaseConfig = {
  apiKey: "AIzaSyA-ClZaEkufcnC_y6LgirCb5nq0h_NxoXg",
  authDomain: "aidrix-93940.firebaseapp.com",
  projectId: "aidrix-93940",
  storageBucket: "aidrix-93940.firebasestorage.app",
  messagingSenderId: "112029014848",
  appId: "1:112029014848:web:f2a3dab73525749a8df8a5",
  measurementId: "G-PFFGNFXS3K"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();
const ADMIN_EMAIL = "admin@aidrix.com";

// 3. UI SWITCHING
window.switchMode = (mode) => {
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    const tabLogin = document.getElementById('tab-login');
    const tabSignup = document.getElementById('tab-signup');
    const title = document.getElementById('modalTitle');

    if (mode === 'login') {
        loginForm.classList.remove('d-none');
        signupForm.classList.add('d-none');
        tabLogin.classList.add('active-tab', 'text-white');
        tabLogin.classList.remove('text-white-50');
        tabSignup.classList.remove('active-tab', 'text-white');
        tabSignup.classList.add('text-white-50');
        title.innerText = "Welcome Back";
    } else {
        loginForm.classList.add('d-none');
        signupForm.classList.remove('d-none');
        tabSignup.classList.add('active-tab', 'text-white');
        tabSignup.classList.remove('text-white-50');
        tabLogin.classList.remove('active-tab', 'text-white');
        tabLogin.classList.add('text-white-50');
        title.innerText = "Join Aidrix";
    }
};

window.toggleWorkerFields = () => {
    const role = document.getElementById('signup-role').value;
    const workerField = document.getElementById('worker-upload-field');
    const fileInput = document.getElementById('signup-id-file');
    
    if (role === 'worker') {
        workerField.classList.remove('d-none');
        fileInput.setAttribute('required', 'true');
    } else {
        workerField.classList.add('d-none');
        fileInput.removeAttribute('required');
    }
};

// --- 4. PASSWORD VALIDATION ---
const passInput = document.getElementById('signup-pass');

const validatePassword = () => {
    const val = passInput.value;
    const len = val.length >= 8;
    const hasUpper = /[A-Z]/.test(val);
    const hasLower = /[a-z]/.test(val);
    const hasNum = /[0-9]/.test(val);
    const hasSpec = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(val); 
    
    updateReq('req-len', len);
    updateReq('req-case', hasUpper && hasLower);
    updateReq('req-num', hasNum);
    updateReq('req-spec', hasSpec);
};

if(passInput) {
    passInput.addEventListener('input', validatePassword);
}

function updateReq(id, valid) {
    const el = document.getElementById(id);
    if (!el) return; 

    if(valid) {
        el.classList.remove('text-danger'); 
        el.classList.add('text-success');   
        if(!el.innerHTML.includes('bi-check')) {
             const cleanText = el.innerText.replace('Min', '').replace('•', '').trim();
             el.innerHTML = `<i class="bi bi-check-lg"></i> ${cleanText}`;
        }
    } else {
        el.classList.add('text-danger');    
        el.classList.remove('text-success'); 
        if(el.innerHTML.includes('bi-check')) {
             const cleanText = el.innerText.trim();
             el.innerHTML = `• ${cleanText}`;
        }
    }
}

// 5. SIGNUP LOGIC
const signupForm = document.getElementById('signup-form');
if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('signup-email').value;
        const pass = document.getElementById('signup-pass').value;
        const role = document.getElementById('signup-role').value;
        const fileInput = document.getElementById('signup-id-file');

        try {
            // A. Create User (No email verification sent)
            const userCredential = await createUserWithEmailAndPassword(auth, email, pass);
            const user = userCredential.user;
            
            // B. Handle ID Image
            let idProofData = null;
            if (role === 'worker' && fileInput.files[0]) {
                idProofData = await convertToBase64(fileInput.files[0]);
            }

            // C. Save to Backend (Workers set to isVerified: false)
            await saveUserToBackend(user, role, idProofData);
            
            if(role === 'worker') {
                alert("Account created! Please wait for Admin approval.");
            } else {
                alert("Account created successfully!");
            }
            
            switchMode('login');

        } catch (error) {
            alert("Signup Error: " + error.message);
        }
    });
}

// Helper: Convert File to Base64
const convertToBase64 = (file) => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result);
        reader.onerror = error => reject(error);
    });
};

// Helper: Save User Role & ID
async function saveUserToBackend(user, role, idProof) {
    try {
        await fetch('/api/user/profile', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                uid: user.uid,
                email: user.email,
                role: role,
                id_proof: idProof, 
                // WORKERS ARE FALSE (Not Verified) by default
                // USERS ARE TRUE (Verified) by default
                isVerified: (role !== 'worker') 
            })
        });
    } catch (e) {
        console.error("Backend Save Error", e);
    }
}

// 6. LOGIN LOGIC
const loginForm = document.getElementById('login-form');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value;
        const pass = document.getElementById('login-pass').value;

        try {
            const userCredential = await signInWithEmailAndPassword(auth, email, pass);
            const user = userCredential.user;

            // REMOVED: The check for !user.emailVerified
            
            const modalEl = document.getElementById('authModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            modal.hide();

            if (user.email === ADMIN_EMAIL) {
                alert("👮‍♂️ ADMIN ACCESS GRANTED");
                window.location.href = "/dashboard/admin";
            } else {
                handleLoginSuccess(user);
            }

        } catch (error) {
            alert("Login Error: " + error.message);
        }
    });
}

// 7. SHARED HELPERS
async function handleLoginSuccess(user) {
    try {
        const res = await fetch(`/api/user/profile?uid=${user.uid}`);
        const data = await res.json();
        const role = data.role || 'user';
        
        if (role === 'worker') window.location.href = "/dashboard/worker";
        else window.location.href = "/dashboard/user";
    } catch (error) {
        window.location.href = "/dashboard/user";
    }
}

const googleBtn = document.getElementById('google-btn');
if(googleBtn) {
    googleBtn.addEventListener('click', async () => {
        try {
            const result = await signInWithPopup(auth, provider);
            handleLoginSuccess(result.user);
        } catch (error) { console.error(error); }
    });
}

onAuthStateChanged(auth, (user) => {
    if (user) {
        const navBtn = document.querySelector('.btn-gradient');
        if(navBtn) {
            if(user.email === ADMIN_EMAIL) {
                 navBtn.innerHTML = `<i class="bi bi-shield-lock-fill"></i> Admin Panel`;
                 navBtn.onclick = () => window.location.href = "/dashboard/admin";
            } else {
                navBtn.innerHTML = `<i class="bi bi-person-circle"></i> ${user.email.split('@')[0]}`;
                navBtn.onclick = () => handleLoginSuccess(user);
            }
            navBtn.removeAttribute('data-bs-toggle');
            navBtn.removeAttribute('data-bs-target');
        }
    }
});