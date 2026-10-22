# Canvas eklentisi

Canvas'ta açık projeleri yerel MCP bağlantısıyla Codex'e okutun; kendi asistanınızı oluşturup `.flowast` paketi olarak dışarı aktarın. Eklenti açık projeleri, kartları, bağlantıları ve agent tanımlarını okuyabilir. Asistan oluşturma ve dışarı aktarma paket dosyaları yazar; projeleri değiştirmez veya asistan çalıştırmaz.

Windows'ta Canvas ve Codex aynı bilgisayarda çalışmalıdır. Canvas ve eklenti aynı sabit yerel HTTP adresini kullanır: `http://127.0.0.1:47321/mcp`. Kullanıcının adres veya config dosyası düzenlemesi gerekmez.

**Gereksinim:** Bu sabit adresi kullanan güncel Canvas sürümü. Asistan oluşturma için uygulamanın `canvas_get_assistant`, `canvas_create_assistant` ve `canvas_export_assistant` araçlarını sunması gerekir. Eklenti yüklemek çalışan Canvas sürümünü güncellemez; uygulama güncellemesinden sonra yeni sürümü açın.

## Kurulum

1. Canvas'ı açın. **Ayarlar → MCP bağlantısı** bölümünde bağlantıyı açın.
2. Codex masaüstü uygulamasında **Eklentiler → Ekle → Pazar yeri ekle** yolunu izleyin.
3. Depo adresi olarak `https://github.com/kbingol/canvas-plugins` girin.
4. Eklenen **Canvas Plugins** kaynağında **Canvas → Yükle** seçin.
5. Aynı bilgisayarda çalışan **yeni bir Codex sohbeti** açın. Canvas açık kalsın.

Denemek için şunu yazın:

> Canvas bağlantısını kontrol et ve açık projelerimi listele.

Ardından bir projeyi adıyla belirterek kartlarını özetlemesini isteyin. Yalnızca bu bilgisayardaki açık Canvas projelerine erişilir. MCP sonuçlarının konuşmada kullanılması istemcinin veri işleme ayarlarına tabidir.

## Kendi asistanınızı oluşturun

Örneğin şunu isteyin:

> Canvas'ta metinleri Türkçeye çeviren bir asistan oluştur ve .flowast olarak dışarı aktar.

Codex, talimatları ve gerekiyorsa skill'leri hazırlar; Canvas bunları doğrulayıp `%LOCALAPPDATA%/Algomim/Canvas/assistants/<id>` klasörüne kaydeder. Yeni asistan uygulamada hemen görünür. Dışarı aktarılan `.flowast` dosyası varsayılan olarak Canvas'ın yerel `Exports` klasörüne yazılır; sonucu dönen dosya yolundan paylaşabilirsiniz. Asistanı kullanmak için Canvas'ta çalıştırın; MCP üzerinden paket oluşturmak modeli veya görsel üretimini başlatmaz.

Mevcut bir asistanın tam tanımı okunabilir ve yüklenmiş paketler dışarı aktarılabilir. Oluşturma mevcut paketin üzerine yazmaz; aynı kimlikle güncelleme veya silme aracı yoktur. `.flowast` dosyasını başka bir Canvas'ta **Ayarlar → Asistanlar → Asistan ekle** ile yükleyebilirsiniz.

Terminalden kurulum isteyenler için:

```powershell
codex plugin marketplace add kbingol/canvas-plugins
codex plugin add canvas@canvas-plugins
```

Kurulumdan sonra yeni oturum başlatın. Bu depo, ekleyebileceğiniz bağımsız bir eklenti kataloğudur; OpenAI'nin resmî herkese açık dizininde listelendiği anlamına gelmez. [OpenAI'nin pazar yeri ve kurulum rehberi](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

## Yardım

Bağlantı kurulamıyorsa [sorun giderme](docs/troubleshooting.md) sayfasına bakın. Paket yapısı ve doğrulama yaklaşımı [mimari notlarında](docs/architecture.md) bulunur. Lisans: [MIT](LICENSE).
