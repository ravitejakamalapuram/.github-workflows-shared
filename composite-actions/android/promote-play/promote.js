const {google} = require('googleapis');
const androidpublisher = google.androidpublisher('v3');

async function promoteToProduction() {
  const auth = new google.auth.GoogleAuth({
    credentials: JSON.parse(process.env.SERVICE_ACCOUNT_JSON),
    scopes: ['https://www.googleapis.com/auth/androidpublisher'],
  });

  const authClient = await auth.getClient();
  google.options({auth: authClient});

  const packageName = process.env.PACKAGE_NAME;
  const sourceTrack = process.env.SOURCE_TRACK;
  const targetTrack = process.env.TARGET_TRACK;
  const rolloutPercentage = parseFloat(process.env.ROLLOUT_PERCENTAGE);
  const updatePriority = parseInt(process.env.UPDATE_PRIORITY);

  console.log(`🚀 Loading Google Play edits for: ${packageName}...`);

  // Create new edit
  const editRes = await androidpublisher.edits.insert({
    packageName: packageName,
  });
  const editId = editRes.data.id;

  try {
    // Get latest version from source track
    const tracksRes = await androidpublisher.edits.tracks.get({
      packageName: packageName,
      editId: editId,
      track: sourceTrack,
    });

    const releases = tracksRes.data.releases || [];
    const sourceRelease = releases.find(r => r.status === 'completed');
    if (!sourceRelease) {
      throw new Error(`No completed release found in ${sourceTrack} track`);
    }

    console.log(`Promoting version codes: ${sourceRelease.versionCodes.join(', ')}`);

    const releaseStatus = rolloutPercentage === 100 ? 'completed' : 'inProgress';
    const userFraction = rolloutPercentage / 100;

    const targetRelease = {
      versionCodes: sourceRelease.versionCodes,
      status: releaseStatus,
      inAppUpdatePriority: updatePriority,
      releaseNotes: sourceRelease.releaseNotes,
    };

    if (rolloutPercentage < 100) {
      targetRelease.userFraction = userFraction;
    }

    // Promote to target track
    await androidpublisher.edits.tracks.update({
      packageName: packageName,
      editId: editId,
      track: targetTrack,
      requestBody: {
        releases: [targetRelease],
      },
    });

    // Commit the edit
    await androidpublisher.edits.commit({
      packageName: packageName,
      editId: editId,
    });

    console.log(`✅ Successfully promoted from ${sourceTrack} to ${targetTrack} at ${rolloutPercentage}% rollout`);
    console.log(`Update priority: ${updatePriority}`);
  } catch (error) {
    console.error('❌ Error occurred, rolling back edit.');
    try {
      await androidpublisher.edits.delete({
        packageName: packageName,
        editId: editId,
      });
    } catch (deleteError) {
      console.error('Failed to delete transaction edit:', deleteError.message);
    }
    throw error;
  }
}

promoteToProduction().catch(error => {
  console.error('❌ Promotion failed:', error.message);
  process.exit(1);
});
