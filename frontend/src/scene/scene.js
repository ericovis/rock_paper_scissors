import * as THREE from 'three';

export function createScene(host, { mobile = false } = {}) {
  const width = host.clientWidth || 800;
  const height = host.clientHeight || 600;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070b14);

  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
  camera.position.set(0, 1.2, 6);
  camera.lookAt(0, 0.4, 0);

  const renderer = new THREE.WebGLRenderer({
    antialias: !mobile,
    powerPreference: mobile ? 'low-power' : 'high-performance',
  });
  renderer.setPixelRatio(mobile ? 1 : Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  renderer.shadowMap.enabled = !mobile;
  host.appendChild(renderer.domElement);

  // --- Lighting ---
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
  keyLight.position.set(4, 6, 4);
  if (!mobile) {
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(1024, 1024);
  }
  scene.add(keyLight);

  if (!mobile) {
    const fillLight = new THREE.DirectionalLight(0x7c9cff, 0.35);
    fillLight.position.set(-4, 2, 3);
    scene.add(fillLight);
  }

  scene.add(new THREE.AmbientLight(0x404060, mobile ? 0.9 : 0.55));

  // --- Ground disk (subtle) ---
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(3.5, mobile ? 16 : 48),
    new THREE.MeshStandardMaterial({ color: 0x121a2c, roughness: 0.9 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.6;
  if (!mobile) ground.receiveShadow = true;
  scene.add(ground);

  // --- Hands ---
  const leftHand = buildHand({ color: 0x7c9cff, mobile });
  leftHand.group.position.set(-1.3, 0.4, 0);
  leftHand.group.rotation.y = Math.PI / 8;
  scene.add(leftHand.group);

  const rightHand = buildHand({ color: 0xff8a7c, mobile });
  rightHand.group.position.set(1.3, 0.4, 0);
  rightHand.group.rotation.y = -Math.PI / 8;
  rightHand.group.scale.x = -1;
  scene.add(rightHand.group);

  leftHand.show('ready');
  rightHand.show('ready');

  // --- Animation loop ---
  let phase = 'idle';
  let revealStartMs = 0;
  let running = true;
  const clock = new THREE.Clock();

  function animate() {
    if (!running) return;
    const dt = clock.getDelta();
    const t = clock.getElapsedTime();

    // Ready-state bob
    if (phase === 'select') {
      const bob = Math.sin(t * 4) * 0.06;
      leftHand.group.position.y = 0.4 + bob;
      rightHand.group.position.y = 0.4 - bob;
    }

    // Reveal animation
    if (phase === 'reveal') {
      const elapsed = (performance.now() - revealStartMs) / 1000;
      const progress = Math.min(1, elapsed / 0.4);
      const eased = easeOutBack(progress);
      leftHand.group.position.y = 0.4 + Math.sin(progress * Math.PI) * 0.15;
      rightHand.group.position.y = 0.4 + Math.sin(progress * Math.PI) * 0.15;
      leftHand.group.rotation.z = (1 - eased) * 0.3;
      rightHand.group.rotation.z = -(1 - eased) * 0.3;
    }

    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  animate();

  // --- Resize handling ---
  const onResize = () => {
    const w = host.clientWidth || 800;
    const h = host.clientHeight || 600;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  };
  const ro = new ResizeObserver(onResize);
  ro.observe(host);

  return {
    setPhase(p) {
      phase = p;
      if (p === 'select') {
        leftHand.show('ready');
        rightHand.show('ready');
        leftHand.group.rotation.z = 0;
        rightHand.group.rotation.z = 0;
      }
    },
    playReveal(yourChoice, opponentChoice, winner) {
      // Left hand = you, right hand = opponent
      leftHand.show(yourChoice || 'ready');
      rightHand.show(opponentChoice || 'ready');
      phase = 'reveal';
      revealStartMs = performance.now();
      // Tint winner
      const youWin = winner === 'you';
      const oppWin = winner === 'opponent';
      leftHand.highlight(youWin);
      rightHand.highlight(oppWin);
    },
    dispose() {
      running = false;
      ro.disconnect();
      renderer.dispose();
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
          else obj.material.dispose();
        }
      });
    },
  };
}

function buildHand({ color, mobile }) {
  const group = new THREE.Group();
  const segments = mobile ? 12 : 24;

  const mat = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.55,
    metalness: 0.1,
  });
  const baseColor = color;

  // Ready: a small loose fist with fingers hinted
  const ready = new THREE.Group();
  {
    const fist = new THREE.Mesh(new THREE.SphereGeometry(0.5, segments, segments), mat);
    ready.add(fist);
  }

  // Rock: tight fist (larger solid sphere)
  const rock = new THREE.Group();
  {
    const fist = new THREE.Mesh(new THREE.SphereGeometry(0.6, segments, segments), mat);
    rock.add(fist);
  }

  // Paper: flat open hand
  const paper = new THREE.Group();
  {
    const palm = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.18, 0.9), mat);
    paper.add(palm);
    for (let i = 0; i < 4; i++) {
      const finger = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.16, 0.55), mat);
      finger.position.set(-0.42 + i * 0.28, 0, 0.7);
      paper.add(finger);
    }
    const thumb = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.16, 0.45), mat);
    thumb.position.set(0.62, 0, 0.1);
    thumb.rotation.y = -Math.PI / 6;
    paper.add(thumb);
  }

  // Scissors: fist with two extended fingers forming a V
  const scissors = new THREE.Group();
  {
    const fist = new THREE.Mesh(new THREE.SphereGeometry(0.46, segments, segments), mat);
    scissors.add(fist);

    const fingerGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.7, mobile ? 8 : 16);
    const f1 = new THREE.Mesh(fingerGeom, mat);
    f1.position.set(-0.1, 0.1, 0.55);
    f1.rotation.x = Math.PI / 2;
    f1.rotation.z = Math.PI / 14;
    scissors.add(f1);

    const f2 = new THREE.Mesh(fingerGeom, mat);
    f2.position.set(0.1, 0.1, 0.55);
    f2.rotation.x = Math.PI / 2;
    f2.rotation.z = -Math.PI / 14;
    scissors.add(f2);
  }

  group.add(ready, rock, paper, scissors);
  const variants = { ready, rock, paper, scissors };
  Object.values(variants).forEach((v) => (v.visible = false));

  return {
    group,
    show(name) {
      Object.entries(variants).forEach(([k, v]) => (v.visible = k === name));
    },
    highlight(on) {
      mat.emissive = new THREE.Color(on ? 0x3ecf8e : 0x000000);
      mat.emissiveIntensity = on ? 0.6 : 0.0;
      mat.color.setHex(baseColor);
    },
  };
}

function easeOutBack(x) {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
}
