# Canvas eklentisi

Canvas'ta açık projeleri Codex'e okutun ve konuşarak flow oluşturun. Eklenti metin ve asistan node'ları ekleyebilir, konumlarını ve metinlerini düzenleyebilir, node'ları bağlayabilir. Kendi asistanınızı oluşturup `.flowast` olarak dışarı aktarabilir veya kişisel asistanlarınızı silebilirsiniz. Flow oluşturmak asistanları çalıştırmaz. Çalıştırmasını istediğinizde Codex, Canvas'ın kendi asistan motorundan akışı başlatabilir ve sonucunu takip edebilir.

Windows'ta Canvas ve Codex aynı bilgisayarda çalışmalıdır. İkisi de `http://127.0.0.1:47321/mcp` adresini kullanır. Adres veya config dosyası düzenlemeniz gerekmez. Eklentiyi güncellemek çalışan Canvas uygulamasına yeni araç eklemez; güncel uygulama sürümünü açın.

## Kurulum

1. Canvas'ı açın. **Ayarlar → MCP bağlantısı** bölümünden bağlantıyı açın.
2. Codex'te **Eklentiler → Ekle → Pazar yeri ekle** yolunu izleyin.
3. Depo adresi olarak `https://github.com/kbingol/canvas-plugins` girin.
4. **Canvas Plugins** kaynağında **Canvas → Yükle** seçin.
5. Aynı bilgisayarda yeni bir Codex sohbeti açın; Canvas açık kalsın.

Bağlantıyı kontrol etmek için:

> Canvas bağlantısını kontrol et ve açık projelerimi listele.

Yalnızca bu bilgisayardaki açık Canvas projelerine erişilir. MCP sonuçlarının konuşmada kullanılması istemcinin veri işleme ayarlarına tabidir.

## Konuşarak flow oluşturun

> Açık Canvas projesinde bir fikir metnini Prompt Assistant'a, onu da Image Assistant'a bağlayan bir flow oluştur.

Codex aktif projenin mevcut node'larını ve kullanılabilir asistanların portlarını okur, ardından yeni node'ları ve bağlantıları aynı projeye ekler. Metinleri ve konumları da değiştirebilir. Flow'lar uygulamanın normal proje düzenleme ve kaydetme yolunu kullanır. Proje oluşturma, node silme ve dosya içe aktarma bu araçlara dahil değildir. Çalıştırma ayrı bir istektir; asistanlar Canvas'ta ayarlanmış hesapları, modelleri ve araçları kullanır.

## Flow'u çalıştırın

> Açık projedeki bu flow'u bağımlılık sırasıyla çalıştır ve sonucu bildir.

Çalıştırma Canvas'ın mevcut asistan motorunu kullanır. Codex node'ları ekranda tıklayarak çalıştırmaz; MCP üzerinden işi başlatır ve durumunu okur. Talimat ve görsel üretimi, Canvas'taki model ve hesap ayarlarıyla gerçekleşir. Sadece flow çizmesini istemek çalıştırma yetkisi vermez.

## Kendi asistanınızı oluşturun

> Canvas'ta metinleri Türkçeye çeviren bir asistan oluştur ve .flowast olarak dışarı aktar.

Canvas tanımı doğrulayıp `%LOCALAPPDATA%/Algomim/Canvas/assistants/<id>` klasörüne kaydeder. Yeni asistan hemen görünür. Dışarı aktarılan `.flowast` dosyası varsayılan olarak Canvas'ın yerel `Exports` klasörüne yazılır; sonuçta dönen dosya yolundan paylaşabilirsiniz. Paket oluşturmak modeli veya görsel üretimini başlatmaz.

Mevcut asistanın tam tanımı okunabilir ve yüklü paketler dışarı aktarılabilir. Oluşturma mevcut paketin üzerine yazmaz; aynı kimlikle paket güncelleme aracı yoktur. Kullanıcının yüklediği veya MCP ile oluşturduğu kişisel paketler silinebilir; uygulamayla gelen hazır paketler korunur. Silme proje node'larını, çıktıları ve dışarı aktarılan dosyaları kaldırmaz. `.flowast` dosyasını başka bir Canvas'ta **Ayarlar → Asistanlar → Asistan ekle** ile yükleyebilirsiniz.

Terminalden kurulum için:

```powershell
codex plugin marketplace add kbingol/canvas-plugins
codex plugin add canvas@canvas-plugins
```

Kurulumdan sonra yeni oturum başlatın. Bu depo bağımsız bir eklenti kataloğudur; OpenAI'nin resmî herkese açık dizininde listelendiği anlamına gelmez. [Pazar yeri ve kurulum rehberi](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

## Yardım

[Bağlantı ve araç sorunları](docs/troubleshooting.md), [paket mimarisi](docs/architecture.md), [doğrulama sonuçları](docs/validation.md). Lisans: [MIT](LICENSE).
