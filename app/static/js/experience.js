/* Aerospace entry and accessible workspace chrome. No business decisions live here. */
(function (global) {
  'use strict';
  var EXPERIENCE_ASSETS = {
    day: '/static/assets/experience/earth-day.webp',
    night: '/static/assets/experience/earth-night.webp',
    clouds: '/static/assets/experience/earth-clouds.webp',
    dayHigh: '/static/assets/experience/earth-day-4k.webp',
    nightHigh: '/static/assets/experience/earth-night-4k.webp',
    fallback: '/static/assets/experience/earth-day-night.webp'
  };
  var preferences = {sound: true, collapsed: false};
  var earthCleanup = null, audioContext = null, shellOptions = {}, shellBound = false;
  var motionQuery = global.matchMedia('(prefers-reduced-motion: reduce)');
  try {preferences.collapsed = localStorage.getItem('tusas:sidebar-collapsed') === '1';} catch (_) {}
  try {preferences.sound = localStorage.getItem('tusas:entry-sound') !== '0';} catch (_) {}
  function escape(value) {return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function icon(name) {
    var paths = {
      arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',
      eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
      sound:'<path d="m11 5-6 4H2v6h3l6 4V5Zm4 3a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
      mute:'<path d="m11 5-6 4H2v6h3l6 4V5Zm5 4 5 6m0-6-5 6"/>',
      panel:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m7-11-3 3 3 3"/>',
      lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
      check:'<path d="m5 12 4 4L19 6"/>'
    };
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">'+(paths[name] || paths.arrow)+'</svg>';
  }
  function reducedMotion() {return motionQuery.matches;}

  function renderExperienceLogin() {
    if (earthCleanup) {earthCleanup(); earthCleanup = null;}
    document.body.classList.remove('experience-workspace');
    return '<div class="experience-login" data-no-translate>'+
      '<div class="experience-space" aria-hidden="true"><picture class="experience-starfield"><source media="(max-width: 720px)" srcset="/static/assets/experience/stars-1280.webp"><img src="/static/assets/experience/stars-1920.webp" srcset="/static/assets/experience/stars-1920.webp 1920w, /static/assets/experience/stars-3840.webp 3840w" sizes="100vw" width="3840" height="2160" alt="" decoding="async"></picture><div class="experience-space-light"></div></div>'+
      '<header class="experience-login-header"><div class="experience-brand-clearspace"><img src="/static/assets/brand/logo-white.png" alt="TUSAŞ — Türk Havacılık Uzay Sanayii" width="200" height="83"></div><span class="experience-product-label">KURUMSAL ÖĞRENME VE YAPAY ZEKÂ</span></header>'+
      '<div class="experience-login-layout"><section class="experience-story" aria-labelledby="experienceStoryTitle">'+
      '<div class="experience-planet-scene" aria-hidden="true"><div class="experience-earth-halo"></div><div class="experience-earth"><img class="experience-earth-fallback" src="'+EXPERIENCE_ASSETS.fallback+'" alt="" decoding="async"><canvas class="experience-earth-canvas" id="experienceEarth"></canvas></div></div>'+
      '<div class="experience-story-copy"><div class="experience-eyebrow"><span></span> ORTAK AKIL. GÜÇLÜ GELECEK.</div><h1 id="experienceStoryTitle">Birlikte gelişiriz.</h1><p>İhtiyaçtan çözüme, aynı çalışma alanında.</p></div></section>'+
      '<section class="experience-auth" aria-labelledby="experienceLoginTitle"><div class="experience-auth-line" aria-hidden="true"></div><div class="experience-auth-kicker">ÇALIŞMA ALANINIZ</div><h2 id="experienceLoginTitle">Hoş geldiniz.</h2><p class="experience-auth-intro">Hesabınızla çalışma alanınıza giriş yapın.</p>'+
      '<form id="portalAccountLogin"><div class="field"><label for="accountUsername">Kullanıcı adı</label><input id="accountUsername" name="username" required maxlength="80" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="Kullanıcı adınız"></div>'+
      '<div class="field"><label for="accountPassword">Parola</label><div class="experience-password"><input id="accountPassword" name="password" type="password" required maxlength="200" autocomplete="current-password" placeholder="Parolanız"><button type="button" id="experiencePasswordToggle" aria-label="Parolayı göster" aria-pressed="false">'+icon('eye')+'</button></div><span class="experience-caps" id="experienceCaps" hidden>Caps Lock açık</span></div>'+
      '<div id="portalLoginError" class="experience-auth-error" role="alert" aria-live="polite"></div><button class="btn primary experience-login-submit" id="experienceLoginSubmit" type="submit"><span>Giriş yap</span>'+icon('arrow')+'</button></form>'+
      '<div class="experience-access-note">'+icon('lock')+'<p>Yetkili olduğunuz çalışma alanı otomatik açılır.<br>Hesap desteği için sistem sorumlunuzla iletişime geçin.</p></div></section></div>'+
      '<footer class="experience-login-footer"><span>TÜRK HAVACILIK UZAY SANAYİİ</span><div><button type="button" class="experience-sound" id="experienceSound" aria-pressed="false" aria-label="Giriş sesini aç">'+icon('mute')+'<span>Giriş sesi kapalı</span></button><span class="experience-footer-divider" aria-hidden="true"></span><span>Bilgiden gelişime, birlikte.</span></div></footer></div>';
  }

  function setSoundButton(button) {
    button.setAttribute('aria-pressed', String(preferences.sound));
    button.setAttribute('aria-label', preferences.sound ? 'Giriş sesini kapat' : 'Giriş sesini aç');
    button.innerHTML = icon(preferences.sound ? 'sound' : 'mute')+'<span>Giriş sesi '+(preferences.sound ? 'açık' : 'kapalı')+'</span>';
  }
  function prepareAudio() {
    try {
      var Audio = global.AudioContext || global.webkitAudioContext;
      if (!Audio) return;
      audioContext = audioContext || new Audio();
      if (audioContext.state === 'suspended') audioContext.resume().catch(function () {});
    } catch (_) {audioContext = null;}
  }
  function playEntrySound() {
    if (!preferences.sound || !audioContext || audioContext.state !== 'running') return;
    try {
      var start = audioContext.currentTime;
      var gain = audioContext.createGain();
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.11, start + 0.24);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.58);
      gain.connect(audioContext.destination);
      [164, 328].forEach(function (frequency, index) {
        var oscillator = audioContext.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(frequency, start);
        oscillator.frequency.exponentialRampToValueAtTime(frequency * 4.4, start + 0.43);
        oscillator.connect(gain);
        oscillator.start(start + index * 0.018);
        oscillator.stop(start + 0.6);
      });
    } catch (_) {}
  }
  function playExperienceEntry(onReady) {
    playEntrySound();
    if (reducedMotion()) {if (earthCleanup) {earthCleanup();earthCleanup=null;} onReady(); return Promise.resolve();}
    var transition = document.createElement('div');
    transition.className = 'experience-entry';
    transition.setAttribute('aria-hidden', 'true');
    transition.inert = true;
    var login = document.querySelector('.experience-login');
    if (login) {
      var scene = login.cloneNode(true);
      scene.querySelectorAll('[id]').forEach(function(node){node.removeAttribute('id');});
      scene.querySelectorAll('input').forEach(function(input){input.value='';input.removeAttribute('value');});
      var canvas=scene.querySelector('canvas');
      try{if(canvas&&earthCleanup&&earthCleanup.snapshot)earthCleanup.snapshot(canvas);else throw new Error('No rendered sphere');}
      catch(_){var earth=scene.querySelector('.experience-earth');if(earth)earth.classList.remove('earth-ready');}
      transition.appendChild(scene);
    }
    if (earthCleanup) {earthCleanup(); earthCleanup = null;}
    document.body.appendChild(transition);
    onReady(); // Authenticated content renders immediately beneath the short transition.
    return new Promise(function (resolve) {
      var complete = false;
      function finish() {if (complete) return; complete = true; transition.remove(); resolve();}
      transition.addEventListener('animationend', function(event){if(event.target===transition)finish();});
      global.setTimeout(finish, 850);
    });
  }
  function bindExperienceLogin(options) {
    options = options || {};
    var form = document.getElementById('portalAccountLogin');
    if (!form || form.dataset.experienceBound) return;
    form.dataset.experienceBound = 'true';
    var password = document.getElementById('accountPassword');
    var toggle = document.getElementById('experiencePasswordToggle');
    if (toggle) toggle.addEventListener('click', function () {
      var visible = password.type === 'password';
      password.type = visible ? 'text' : 'password';
      toggle.setAttribute('aria-pressed', String(visible));
      toggle.setAttribute('aria-label', visible ? 'Parolayı gizle' : 'Parolayı göster');
      password.focus({preventScroll: true});
    });
    password.addEventListener('keyup', function (event) {
      document.getElementById('experienceCaps').hidden = !(event.getModifierState && event.getModifierState('CapsLock'));
    });
    password.addEventListener('blur', function () {document.getElementById('experienceCaps').hidden = true;});
    var sound = document.getElementById('experienceSound');
    setSoundButton(sound);
    sound.addEventListener('click', function () {preferences.sound = !preferences.sound; try{localStorage.setItem('tusas:entry-sound',preferences.sound?'1':'0');}catch(_){} if (preferences.sound) {prepareAudio();playEntrySound();} setSoundButton(sound);});
    var fallback = document.querySelector('.experience-earth-fallback');
    if (fallback) fallback.addEventListener('error', function () {fallback.hidden = true;}, {once: true});
    earthCleanup = mountEarth(document.getElementById('experienceEarth'));
    if (typeof options.authenticate !== 'function') return;
    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      if (form.dataset.busy === 'true') return;
      if(preferences.sound)prepareAudio();
      var username = document.getElementById('accountUsername').value.trim();
      if (!username) {document.getElementById('accountUsername').focus(); return;}
      var button = document.getElementById('experienceLoginSubmit');
      var errorBox = document.getElementById('portalLoginError');
      form.dataset.busy = 'true'; form.setAttribute('aria-busy', 'true'); button.disabled = true; errorBox.textContent = '';
      button.innerHTML = '<span class="spinner" aria-hidden="true"></span><span>Giriş yapılıyor…</span>';
      try {
        var session = await options.authenticate({username: username, password: password.value});
        if (!form.isConnected) return;
        button.innerHTML = '<span>Çalışma alanınız açılıyor</span>'+icon('check');
        await playExperienceEntry(function () {if (typeof options.onAuthenticated === 'function') options.onAuthenticated(session);});
      } catch (error) {
        if (!form.isConnected) return;
        errorBox.textContent = error.message || 'Giriş tamamlanamadı. Kullanıcı adı ve parolanızı kontrol edin.';
        password.setAttribute('aria-describedby', 'portalLoginError');
        button.disabled = false; button.innerHTML = '<span>Giriş yap</span>'+icon('arrow');
      } finally {
        form.dataset.busy = 'false'; form.setAttribute('aria-busy', 'false');
      }
    });
  }

  /* A single ray-traced sphere with two real Earth maps. Rendering is capped at
     24 fps and pauses in hidden tabs; a still image remains if WebGL is absent. */
  function mountEarth(canvas) {
    if (!canvas) return function () {};
    function still(){
      var image=canvas.parentElement&&canvas.parentElement.querySelector('.experience-earth-fallback');
      if(image){image.sizes=Math.ceil(canvas.clientWidth||1024)+'px';image.srcset=EXPERIENCE_ASSETS.fallback+' 1024w, /static/assets/experience/earth-still-2k.webp 2048w, /static/assets/experience/earth-still-4k.webp 4096w';}
      return function(){};
    }
    var gl;
    try {gl = canvas.getContext('webgl', {alpha: true, antialias: false, powerPreference: 'low-power', preserveDrawingBuffer: false});} catch (_) {return still();}
    if (!gl) return still();
    var stopped = false, frame = 0, last = 0, textures = [], loaded = 0;
    var angle = 0, previousFrame = null, program;
    var vertex = 'attribute vec2 p; varying vec2 uv; void main(){uv=p;gl_Position=vec4(p,0.,1.);}';
    var precision=gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER,gl.HIGH_FLOAT).precision?'highp':'mediump';
    var fragment = 'precision '+precision+' float; varying vec2 uv; uniform sampler2D dayMap; uniform sampler2D nightMap; uniform sampler2D cloudMap; uniform float rotation;'+
      'void main(){float r=dot(uv,uv);if(r>1.0){gl_FragColor=vec4(0.);return;}vec3 n=vec3(uv.x,uv.y,sqrt(1.-r));'+
      'float ct=cos(-.40),st=sin(-.40);vec3 tilted=vec3(ct*n.x-st*n.y,st*n.x+ct*n.y,n.z);tilted=vec3(tilted.x,.949*tilted.y+.315*tilted.z,-.315*tilted.y+.949*tilted.z);'+
      'float cr=cos(rotation),sr=sin(rotation);vec3 geo=vec3(cr*tilted.x+sr*tilted.z,tilted.y,-sr*tilted.x+cr*tilted.z);'+
      'vec2 coord=vec2(atan(geo.z,geo.x)/6.2831853+.5,asin(clamp(geo.y,-1.,1.))/3.1415926+.5);'+
      'vec3 day=texture2D(dayMap,coord).rgb;vec3 night=texture2D(nightMap,coord).rgb;float cloud=texture2D(cloudMap,coord).r;'+
      'float light=dot(n,normalize(vec3(-.98,.16,.015)));float terminator=smoothstep(-.09,.12,light);'+
      'float luminance=dot(day,vec3(.2126,.7152,.0722));day=mix(vec3(luminance),day,1.15);day=pow(max(day,vec3(0.)),vec3(.83));'+
      'float cloudShadow=texture2D(cloudMap,coord+vec2(.002,-.001)).r;day*=1.-cloudShadow*.16;day=mix(day,vec3(.95,.97,1.),smoothstep(.10,.90,cloud)*.92);'+
      'float cities=smoothstep(.018,.19,max(night.r,night.g)-night.b*.65);vec3 nightColor=night*.065+night*vec3(1.32,1.03,.70)*cities*1.30;'+
      'nightColor*=1.-cloud*.23;nightColor+=vec3(.025,.038,.07)*cloud;'+
      'vec3 color=day*(.15+max(light,0.)*1.10)*terminator+nightColor*(1.-terminator);'+
      'float rim=pow(1.-n.z,3.6);color+=vec3(.16,.39,.68)*rim*(.24+.68*max(light,0.));'+
      'float edge=1.-smoothstep(.996,1.,r);gl_FragColor=vec4(color,edge);}';
    function shader(type, source) {
      var compiled = gl.createShader(type);gl.shaderSource(compiled, source);gl.compileShader(compiled);
      if (!gl.getShaderParameter(compiled, gl.COMPILE_STATUS)) {gl.deleteShader(compiled); return null;}
      return compiled;
    }
    try {
      var vs = shader(gl.VERTEX_SHADER, vertex), fs = shader(gl.FRAGMENT_SHADER, fragment);
      if (!vs || !fs) return still();
      program = gl.createProgram();gl.attachShader(program, vs);gl.attachShader(program, fs);gl.linkProgram(program);
      gl.deleteShader(vs);gl.deleteShader(fs);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {gl.deleteProgram(program);return still();}
      gl.useProgram(program);
      var buffer = gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER, buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
      var location = gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,2,gl.FLOAT,false,0,0);
      gl.uniform1i(gl.getUniformLocation(program,'dayMap'),0);gl.uniform1i(gl.getUniformLocation(program,'nightMap'),1);gl.uniform1i(gl.getUniformLocation(program,'cloudMap'),2);
      var clearCloud=gl.createTexture();textures.push(clearCloud);gl.activeTexture(gl.TEXTURE2);gl.bindTexture(gl.TEXTURE_2D,clearCloud);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,1,1,0,gl.RGB,gl.UNSIGNED_BYTE,new Uint8Array([0,0,0]));gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      var rotationLocation = gl.getUniformLocation(program,'rotation');
      var compact=global.innerWidth<=720||(global.navigator.connection||{}).saveData;
      var renderLimit=Math.min(compact?1024:2160,gl.getParameter(gl.MAX_RENDERBUFFER_SIZE));
      var highMaps=!compact&&canvas.clientWidth*Math.min(global.devicePixelRatio||1,2)>900&&gl.getParameter(gl.MAX_TEXTURE_SIZE)>=4096;
      function render(now) {
        if (stopped || !canvas.isConnected) return;
        if(previousFrame!==null&&!reducedMotion()&&!document.hidden)angle+=Math.min(now-previousFrame,100)/720000*6.2831853;
        previousFrame=now;
        if (loaded === 2 && !document.hidden && (now - last > 1000/24 || reducedMotion())) {
          last = now;
          var size = Math.min(renderLimit, Math.round(canvas.clientWidth * Math.min(global.devicePixelRatio || 1, 2)));
          if (size > 0) {
            if (canvas.width !== size) {canvas.width = size;canvas.height = size;gl.viewport(0,0,size,size);}
            gl.uniform1f(rotationLocation, 1.42 + angle);
            gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
            canvas.parentElement.classList.add('earth-ready');
          }
        }
        if (!reducedMotion() && !document.hidden) frame = requestAnimationFrame(render);
      }
      function resume() {cancelAnimationFrame(frame);previousFrame=null;if (!stopped && !document.hidden && loaded === 2 && canvas.isConnected) frame=requestAnimationFrame(render);}
      document.addEventListener('visibilitychange',resume);
      motionQuery.addEventListener('change',resume);
      [highMaps?EXPERIENCE_ASSETS.dayHigh:EXPERIENCE_ASSETS.day,highMaps?EXPERIENCE_ASSETS.nightHigh:EXPERIENCE_ASSETS.night,EXPERIENCE_ASSETS.clouds].forEach(function (url, index) {
        var image = new Image();
        image.onerror=function(){if(index<2&&!stopped){stopped=true;cancelAnimationFrame(frame);still();}};
        image.onload = function () {
          if (stopped) return;
          var texture = gl.createTexture();textures.push(texture);gl.activeTexture(gl.TEXTURE0+index);gl.bindTexture(gl.TEXTURE_2D,texture);
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,image);
          gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
          if(index<2)loaded++;if(loaded===2) resume();
        };
        image.src=url;
      });
      var cleanup=function () {stopped=true;cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',resume);motionQuery.removeEventListener('change',resume);textures.forEach(function(t){gl.deleteTexture(t);});gl.deleteBuffer(buffer);gl.deleteProgram(program);};
      cleanup.snapshot=function(target){target.width=canvas.width;target.height=canvas.height;gl.drawArrays(gl.TRIANGLE_STRIP,0,4);target.getContext('2d').drawImage(canvas,0,0);};
      return cleanup;
    } catch (_) {still();return function () {stopped=true;cancelAnimationFrame(frame);};}
  }

  function setCollapsed(value) {
    preferences.collapsed = !!value;
    document.body.classList.toggle('experience-sidebar-collapsed', preferences.collapsed);
    var button = document.getElementById('experienceCollapse');
    if (button) {button.setAttribute('aria-expanded',String(!preferences.collapsed));button.setAttribute('aria-label',preferences.collapsed?'Kenar çubuğunu genişlet':'Kenar çubuğunu daralt');button.title=button.getAttribute('aria-label');}
    try {localStorage.setItem('tusas:sidebar-collapsed',preferences.collapsed?'1':'0');} catch (_) {}
  }
  function openSearch() {
    if (typeof shellOptions.onSearch === 'function') {shellOptions.onSearch();return;}
    if (!global.PORTAL || !global.PORTAL.user || !global.state) return;
    global.PORTAL.adminTab='requests';global.PORTAL.filter='';global.PORTAL.offset=0;
    global.state.currentPage=global.PORTAL.isAdmin?'admin-panel':'portal-requests';
    global.render();
    var input=document.getElementById('portalSearch');if(input)input.focus({preventScroll:true});
  }
  function enhanceExperienceShell(options) {
    shellOptions=options||{};
    var user=shellOptions.user||(global.PORTAL&&global.PORTAL.user), sidebar=document.getElementById('sidebar');
    if (!user || !sidebar) return;
    document.body.classList.add('experience-workspace');
    if (earthCleanup) {earthCleanup();earthCleanup=null;}
    var collapse=document.getElementById('experienceCollapse');
    if (!collapse) {collapse=document.createElement('button');collapse.id='experienceCollapse';collapse.type='button';collapse.className='experience-collapse';collapse.setAttribute('aria-controls','sidebar');collapse.innerHTML=icon('panel');sidebar.prepend(collapse);collapse.addEventListener('click',function(){setCollapsed(!preferences.collapsed);});}
    sidebar.querySelectorAll('.nav button').forEach(function(button){
      var label=button.textContent.trim();button.title=label;button.setAttribute('aria-label',label);
      Array.from(button.childNodes).forEach(function(node){if(node.nodeType===3&&node.textContent.trim()){var span=document.createElement('span');span.className='experience-nav-text';span.textContent=node.textContent;node.replaceWith(span);}});
    });
    var profile=document.getElementById('experienceProfile');
    var name=user.display_name||user.username||'Kullanıcı';
    var initials=name.split(/\s+/).map(function(part){return part[0]||'';}).slice(0,2).join('').toLocaleUpperCase('tr-TR');
    if(profile)profile.innerHTML='<span class="experience-avatar" aria-hidden="true">'+escape(initials)+'</span><span class="experience-profile-name">'+escape(name)+'<small>'+escape(user.role_label||'Çalışma alanı')+'</small></span>';
    var breadcrumb=document.getElementById('experienceBreadcrumb');
    var page=shellOptions.page||(global.state&&global.state.currentPage);
    var labels={'submitter-home':'Çalışma alanı / Genel bakış','submitter-request':'Çalışma alanı / Yeni talep','portal-requests':'Çalışma alanı / Taleplerim','portal-resolved':'Çalışma alanı / Tamamlananlar','portal-detail':'Talepler / Talep ayrıntısı','admin-panel':'Çalışma alanı / İş merkezi'};
    if(breadcrumb)breadcrumb.textContent=labels[page]||'Kurumsal çalışma alanı';
    var search=document.getElementById('experienceSearch');if(search)search.onclick=openSearch;
    setCollapsed(preferences.collapsed);
    if(!shellBound){shellBound=true;document.addEventListener('keydown',function(event){if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'&&global.PORTAL&&global.PORTAL.user){event.preventDefault();openSearch();}});}
  }

  global.renderExperienceLogin=renderExperienceLogin;
  global.bindExperienceLogin=bindExperienceLogin;
  global.playExperienceEntry=playExperienceEntry;
  global.enhanceExperienceShell=enhanceExperienceShell;
  global.EXPERIENCE_ASSETS=EXPERIENCE_ASSETS;
})(window);
